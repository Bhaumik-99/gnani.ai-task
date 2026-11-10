import asyncio
import json
import re
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.gnani.prisma import PrismaStream
from app.gnani.timbre import TimbreStreamer
from app.risk.evon import EvonClient, EvonNotConfigured
from app.risk.rules import analyse_explicit_request
from app.schemas import SessionCreate, ThreatResult
from app.sessions.rate_limit import normalize_client_ip
from app.sessions.store import SessionStore
from app.sessions.tokens import issue_session_token, verify_session_token

settings = get_settings()
store = SessionStore(settings.redis_url, settings.session_ttl_seconds)
evon = EvonClient(settings)
timbre = TimbreStreamer(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await store.start()
    await evon.start()
    try:
        yield
    finally:
        await evon.close()
        await store.close()


app = FastAPI(title="VaaniShield API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "vaanishield-api"}


@app.get("/ready")
async def ready():
    try:
        redis_ready = await store.ping()
    except Exception:
        redis_ready = False
    if settings.environment == "production" and not redis_ready:
        raise HTTPException(status_code=503, detail="Required session store is unavailable")
    return {
        "status": "ready" if redis_ready else "degraded",
        "session_store": store.backend if redis_ready else "unavailable",
        "prisma_configured": bool(settings.gnani_api_key and settings.prisma_ws_url),
        "timbre_configured": bool(settings.gnani_api_key and settings.timbre_ws_url),
        "evon_configured": bool(settings.evon_base_url),
    }


@app.get("/api/config")
async def public_config():
    prisma_ready = bool(settings.gnani_api_key and settings.prisma_ws_url)
    timbre_ready = bool(settings.gnani_api_key and settings.timbre_ws_url)
    evon_ready = bool(settings.evon_base_url)
    return {
        "language": settings.prisma_language_code,
        "prisma_sample_rate": settings.prisma_sample_rate,
        "providers": [
            {"provider": "prisma", "model": settings.prisma_model, "configured": prisma_ready},
            {"provider": "evon", "model": settings.evon_model, "configured": evon_ready},
            {"provider": "timbre", "model": settings.timbre_model, "configured": timbre_ready},
        ],
        "live_inference_enabled": prisma_ready,
        "assistant_enabled": prisma_ready and evon_ready and timbre_ready,
        "note": "Prisma and Timbre use Gnani APIs. Evon v3.3 is open-weight and must be served through a compatible vLLM endpoint. Configured means settings are present, not that a live health check succeeded.",
    }


@app.post("/api/sessions")
async def create_session(body: SessionCreate, request: Request):
    client = normalize_client_ip(request.client.host if request.client else None)
    if not await store.allow_rate_limit(client, settings.max_sessions_per_minute):
        raise HTTPException(status_code=429, detail="Too many sessions created. Try again shortly.")
    session_id = str(uuid4())
    await store.set(session_id, {
        "session_id": session_id,
        "session_type": body.session_type,
        "language": body.language,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "created",
    })
    token = issue_session_token(session_id, settings.session_signing_secret, settings.session_ttl_seconds)
    return {"session_id": session_id, "session_type": body.session_type, "token": token, "expires_in": settings.session_ttl_seconds}


async def send_json(ws: WebSocket, lock: asyncio.Lock, event: str, payload: dict):
    async with lock:
        await ws.send_json({"event": event, "payload": payload})


async def send_bytes(ws: WebSocket, lock: asyncio.Lock, chunk: bytes):
    async with lock:
        await ws.send_bytes(chunk)


async def speak(text: str, ws: WebSocket, lock: asyncio.Lock, cancel: asyncio.Event):
    if not settings.gnani_api_key or cancel.is_set():
        return
    await timbre.synthesize(
        text,
        lambda chunk: send_bytes(ws, lock, chunk),
        lambda event: send_json(ws, lock, event["event"], event["payload"]),
        cancel,
    )


_SUSPICIOUS_CONTEXT = re.compile(
    r"kyc|link|click|block|suspend|freeze|police|arrest|cbi|customs|parcel|courier|lottery|prize|refund|transfer|money|pay|rupaye|paise|qr|scan|verify|bank|account|otp|pin|cvv|password|anydesk|teamviewer"
    r"|केवाईसी|लिंक|क्लिक|ब्लॉक|बंद|पुलिस|अरेस्ट|कस्टम्स|पार्सल|लॉटरी|इनाम|पैसे|रुपये|ट्रांसफर|बैंक|खाता|वेरिफाई|ओटीपी|पिन|एनीडेस्क",
    re.I,
)
_RISK_BAND_DEFAULTS = {"medium": (40, 69, 55), "high": (70, 89, 80), "critical": (90, 100, 95)}


def _detect_explicit_with_context(text: str, transcript_history: list[str]) -> ThreatResult | None:
    direct = analyse_explicit_request(text)
    if direct is not None:
        return direct
    if len(transcript_history) >= 2 and analyse_explicit_request(transcript_history[-2]) is None:
        combined = analyse_explicit_request(f"{transcript_history[-2]} {text}")
        if combined is not None:
            return combined
    if len(transcript_history) >= 3 and analyse_explicit_request(f"{transcript_history[-3]} {transcript_history[-2]}") is None:
        combined = analyse_explicit_request(f"{transcript_history[-3]} {transcript_history[-2]} {text}")
        if combined is not None:
            return combined
    return None


def _validate_evon_threat(result: dict, text: str) -> ThreatResult:
    scam_detected = result.get("scam_detected")
    if not isinstance(scam_detected, bool):
        raise ValueError("scam_detected must be a boolean")
    raw_signals = result.get("signals")
    signals = (
        [item.strip()[:64] for item in raw_signals[:12] if isinstance(item, str) and item.strip()]
        if isinstance(raw_signals, list)
        else []
    )
    risk_level = result.get("risk_level", "low")
    risk_score = result.get("risk_score", 0)
    scam_type = str(result.get("scam_type") or "unknown")[:80]
    explanation = str(result.get("explanation") or "")[:500]
    recommended_action = result.get("recommended_action", "continue_with_caution")
    warning_message = str(result.get("warning_message") or "Be cautious and do not share sensitive information.")[:300]

    if scam_detected:
        if risk_level == "low":
            risk_level = "medium"
        if risk_level in _RISK_BAND_DEFAULTS:
            lo, hi, mid = _RISK_BAND_DEFAULTS[risk_level]
            if not isinstance(risk_score, int) or isinstance(risk_score, bool) or not (lo <= risk_score <= hi):
                risk_score = mid
        if recommended_action == "continue_with_caution":
            recommended_action = "end_call" if risk_level == "critical" else "warn_user"
        if not signals and scam_type:
            signals = [scam_type[:64]]

    return ThreatResult.model_validate({
        "risk_level": risk_level,
        "risk_score": risk_score,
        "confidence": result.get("confidence"),
        "scam_detected": scam_detected,
        "scam_type": scam_type,
        "signals": signals,
        "evidence": [{"text": text[:240], "category": "model_context"}] if scam_detected else [],
        "explanation": explanation,
        "recommended_action": recommended_action,
        "warning_message": warning_message,
    })


async def _emit_threat_and_warn(
    threat: ThreatResult,
    ws: WebSocket,
    lock: asyncio.Lock,
    cancel: asyncio.Event,
    alerted: set[str],
    speak_warning: bool = True,
):
    await send_json(ws, lock, "threat.detected", threat.model_dump())
    if speak_warning and threat.scam_type not in alerted:
        alerted.add(threat.scam_type)
        try:
            await speak(threat.warning_message, ws, lock, cancel)
        except asyncio.CancelledError:
            raise
        except Exception:
            await send_json(ws, lock, "audio.output.error", {"message": "Spoken warning is unavailable."})


async def _classify_contextual_scam(
    text: str,
    context: list[str],
    ws: WebSocket,
    lock: asyncio.Lock,
    cancel: asyncio.Event,
    alerted: set[str],
    scam_lock: asyncio.Lock,
    emit_status: bool = True,
    speak_warning: bool = True,
):
    async with scam_lock:
        try:
            result = await evon.classify_scam(text, context)
        except EvonNotConfigured:
            if emit_status:
                await send_json(ws, lock, "analysis.status", {"mode": "deterministic_only", "reason": "Evon endpoint is not configured."})
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            if emit_status:
                await send_json(ws, lock, "analysis.status", {"mode": "deterministic_only", "reason": "Evon unavailable; deterministic rules remain active."})
            return
    if cancel.is_set():
        return
    if not result:
        if emit_status:
            await send_json(ws, lock, "analysis.status", {"mode": "uncertain", "reason": "Evon did not return structured JSON."})
        return
    try:
        threat = _validate_evon_threat(result, text)
    except Exception:
        if emit_status:
            await send_json(ws, lock, "analysis.status", {"mode": "uncertain", "reason": "Evon returned an invalid risk schema."})
        return
    if threat.scam_detected:
        await _emit_threat_and_warn(threat, ws, lock, cancel, alerted, speak_warning=speak_warning)
    elif emit_status:
        await send_json(ws, lock, "analysis.status", {"mode": "analysed", "risk_level": threat.risk_level, "risk_score": threat.risk_score})


async def analyse_turn(
    session_type: str,
    text: str,
    transcript_history: list[str],
    conversation_history: list[dict[str, str]],
    ws: WebSocket,
    lock: asyncio.Lock,
    cancel: asyncio.Event,
    alerted: set[str],
    scam_lock: asyncio.Lock,
    tasks: set[asyncio.Task] | None = None,
):
    if cancel.is_set():
        return

    deterministic = _detect_explicit_with_context(text, transcript_history)
    if deterministic:
        if session_type == "assistant":
            await send_json(ws, lock, "assistant.message", {"text": deterministic.warning_message})
        await _emit_threat_and_warn(deterministic, ws, lock, cancel, alerted, speak_warning=True)
        return

    if session_type == "scam_demo":
        await _classify_contextual_scam(
            text,
            transcript_history,
            ws,
            lock,
            cancel,
            alerted,
            scam_lock,
            emit_status=True,
            speak_warning=True,
        )
        return

    try:
        response = await evon.respond(text, conversation_history)
    except EvonNotConfigured:
        await send_json(ws, lock, "assistant.error", {"code": "EVON_NOT_CONFIGURED", "message": "Configure the Evon vLLM endpoint to enable Vaani."})
        return
    except asyncio.CancelledError:
        raise
    except Exception:
        await send_json(ws, lock, "assistant.error", {"code": "EVON_UNAVAILABLE", "message": "Vaani could not generate a response. Please try again."})
        return
    if cancel.is_set():
        return
    conversation_history.append({"role": "user", "content": text})
    conversation_history.append({"role": "assistant", "content": response})
    del conversation_history[:-12]
    await send_json(ws, lock, "assistant.message", {"text": response})
    if _SUSPICIOUS_CONTEXT.search(text):
        bg_task = asyncio.create_task(
            _classify_contextual_scam(
                text,
                transcript_history.copy(),
                ws,
                lock,
                asyncio.Event(),
                alerted,
                scam_lock,
                emit_status=False,
                speak_warning=False,
            )
        )
        if tasks is not None:
            tasks.add(bg_task)
            bg_task.add_done_callback(tasks.discard)
    try:
        await speak(response, ws, lock, cancel)
    except asyncio.CancelledError:
        raise
    except Exception:
        await send_json(ws, lock, "audio.output.error", {"message": "Speech synthesis is unavailable."})


@app.websocket("/ws/sessions/{session_id}")
async def session_socket(ws: WebSocket, session_id: str):
    offered = [item.strip() for item in ws.headers.get("sec-websocket-protocol", "").split(",")]
    token = next((item.removeprefix("session.") for item in offered if item.startswith("session.")), "")
    origin = ws.headers.get("origin")
    if not origin or origin.rstrip("/") not in settings.cors_origin_list:
        await ws.close(code=4403, reason="Origin not allowed")
        return
    session = await store.get(session_id)
    if not session or not verify_session_token(token, session_id, settings.session_signing_secret):
        await ws.close(code=4401, reason="Invalid or expired session capability")
        return
    claim_owner = uuid4().hex
    if not await store.claim(session_id, owner=claim_owner):
        await ws.close(code=4409, reason="Session already has an active connection")
        return

    await ws.accept(subprotocol="vaanishield.v1")
    lock = asyncio.Lock()
    scam_lock = asyncio.Lock()
    session_type = session["session_type"]
    deadline = asyncio.get_running_loop().time() + settings.session_ttl_seconds
    context: list[str] = []
    conversation_history: list[dict[str, str]] = []
    alerted: set[str] = set()
    tasks: set[asyncio.Task] = set()
    active_turn: asyncio.Task | None = None
    cancel = asyncio.Event()
    prisma: PrismaStream | None = None
    prisma_task: asyncio.Task | None = None
    frame_count = 0
    frame_window = asyncio.get_running_loop().time()
    max_frames_per_second = int(settings.prisma_sample_rate / 512 * 1.5) + 8

    await send_json(ws, lock, "session.ready", {"session_id": session_id, "session_type": session_type})

    async def start_turn(text: str, source: str):
        nonlocal active_turn, cancel
        text = " ".join(text.split())[:settings.max_transcript_chars]
        if not text:
            return None
        if session_type == "assistant" and active_turn is not None and not active_turn.done():
            cancel.set()
            active_turn.cancel()
            await asyncio.gather(active_turn, return_exceptions=True)
        context.append(text)
        del context[:-12]
        await send_json(ws, lock, "transcript.final", {"text": text, "source": source})
        turn_cancel = asyncio.Event() if session_type == "scam_demo" else cancel
        if session_type == "assistant":
            cancel = asyncio.Event()
            turn_cancel = cancel
        task = asyncio.create_task(
            analyse_turn(
                session_type,
                text,
                context.copy(),
                conversation_history,
                ws,
                lock,
                turn_cancel,
                alerted,
                scam_lock,
                tasks,
            )
        )
        active_turn = task
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return task

    async def pump_prisma():
        assert prisma is not None
        try:
            async for event in prisma.events():
                kind = event.get("type")
                if kind == "transcript":
                    if event.get("is_final") is False:
                        await send_json(ws, lock, "transcript.partial", {"text": str(event.get("text", ""))[:settings.max_transcript_chars]})
                    else:
                        await send_json(ws, lock, "transcript.meta", {
                            "segment_id": event.get("segment_id"),
                            "latency_ms": event.get("latency"),
                            "detected_language_code": event.get("detected_language_code"),
                        })
                        await start_turn(str(event.get("text", "")), "prisma")
                elif kind == "speech_start":
                    await send_json(ws, lock, "speech.start", {"utterance_id": event.get("utterance_id")})
                elif kind == "processing":
                    await send_json(ws, lock, "transcript.processing", {})
                elif kind == "error":
                    await send_json(ws, lock, "provider.error", {"provider": "prisma", "message": "Prisma reported a transcription error."})
        except asyncio.CancelledError:
            raise
        except Exception:
            with suppress(Exception):
                await send_json(ws, lock, "provider.status", {"provider": "prisma", "status": "disconnected"})

    try:
        if settings.gnani_api_key:
            prisma = PrismaStream(settings)
            try:
                handshake = await prisma.connect(session.get("language", settings.prisma_language_code))
                await send_json(ws, lock, "provider.status", {
                    "provider": "prisma", "status": "connected", "model": settings.prisma_model,
                    "request_id": handshake.get("request_id"), "sample_rate": settings.prisma_sample_rate,
                })
                prisma_task = asyncio.create_task(pump_prisma())
            except Exception:
                await send_json(ws, lock, "provider.status", {"provider": "prisma", "status": "unavailable"})
                await prisma.close()
                prisma = None
        else:
            await send_json(ws, lock, "provider.status", {"provider": "prisma", "status": "not_configured"})

        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                await send_json(ws, lock, "session.expired", {})
                break
            try:
                message = await asyncio.wait_for(ws.receive(), timeout=remaining)
            except asyncio.TimeoutError:
                await send_json(ws, lock, "session.expired", {})
                break
            if message.get("type") == "websocket.disconnect":
                break
            audio = message.get("bytes")
            if audio is not None:
                if len(audio) != 1024:
                    await send_json(ws, lock, "error", {"code": "INVALID_AUDIO_FRAME", "message": "Expected 1,024 bytes of mono PCM16LE."})
                    continue
                now = asyncio.get_running_loop().time()
                if now - frame_window >= 1:
                    frame_window, frame_count = now, 0
                frame_count += 1
                if frame_count > max_frames_per_second:
                    await send_json(ws, lock, "error", {"code": "AUDIO_RATE_EXCEEDED", "message": "Audio frames exceed realtime cadence."})
                    await ws.close(code=4408, reason="Audio rate exceeded")
                    break
                if prisma:
                    try:
                        await prisma.send_audio(audio)
                    except Exception:
                        await send_json(ws, lock, "provider.status", {"provider": "prisma", "status": "disconnected"})
                        await prisma.close()
                        prisma = None
                continue

            raw = message.get("text")
            if not raw:
                continue
            if len(raw) > 8192:
                await send_json(ws, lock, "error", {"code": "EVENT_TOO_LARGE", "message": "Control event too large."})
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                await send_json(ws, lock, "error", {"code": "INVALID_EVENT", "message": "Expected a JSON object."})
                continue
            if not isinstance(event, dict) or not isinstance(event.get("payload", {}), dict):
                await send_json(ws, lock, "error", {"code": "INVALID_EVENT", "message": "Payload must be an object."})
                continue
            kind, payload = event.get("event"), event.get("payload", {})
            if kind == "session.start":
                await send_json(ws, lock, "session.started", {"live_transcription": prisma is not None})
            elif kind == "transcript.demo" and session_type == "scam_demo":
                text = payload.get("text", "")
                if not isinstance(text, str) or len(text) > settings.max_transcript_chars:
                    await send_json(ws, lock, "error", {"code": "INVALID_TRANSCRIPT", "message": "Invalid demo transcript."})
                    continue
                task = await start_turn(text, "demo_input")
                await send_json(ws, lock, "transcript.demo_ack", {})
                if task:
                    await asyncio.gather(task, return_exceptions=True)
            elif kind == "assistant.interrupt" and session_type == "assistant":
                cancel.set()
                if active_turn and not active_turn.done():
                    active_turn.cancel()
                    await asyncio.gather(active_turn, return_exceptions=True)
                await send_json(ws, lock, "assistant.interrupted", {"accepted": True})
            elif kind == "session.end":
                cancel.set()
                for task in list(tasks):
                    task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                await send_json(ws, lock, "session.ended", {})
                break
            else:
                await send_json(ws, lock, "error", {"code": "UNKNOWN_EVENT", "message": "Unsupported event."})
    except WebSocketDisconnect:
        pass
    finally:
        cancel.set()
        for task in list(tasks):
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if prisma_task:
            prisma_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await prisma_task
        if prisma:
            with suppress(Exception):
                await prisma.close()
        if await store.release(session_id, owner=claim_owner):
            await store.delete(session_id)
