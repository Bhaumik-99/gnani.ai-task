import base64
import binascii
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.gnani.adapters import GnaniAdapters
from app.schemas import SessionCreate
from app.scam_rules import analyse_explicit_request

settings = get_settings()
app = FastAPI(title="VaaniShield API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
sessions: dict[str, dict] = {}
gnani = GnaniAdapters(settings)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "vaanishield-api"}


@app.get("/api/config")
async def public_config():
    return {
        "language": "hi-en",
        "providers": gnani.statuses(),
        "live_inference_enabled": False,
        "note": "Verify and implement official Gnani API contracts before enabling live inference.",
    }


@app.post("/api/sessions")
async def create_session(body: SessionCreate):
    session_id = str(uuid4())
    sessions[session_id] = {
        "session_type": body.session_type,
        "language": body.language,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_sequence": -1,
        "status": "created",
    }
    return {"session_id": session_id, "session_type": body.session_type}


@app.websocket("/ws/sessions/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str):
    session = sessions.get(session_id)
    if session is None:
        await websocket.close(code=4404, reason="Unknown session")
        return
    await websocket.accept()
    session["status"] = "connected"
    await websocket.send_json({"event": "session.ready", "payload": {
        "session_id": session_id, "session_type": session["session_type"],
        "provider_status": "not_configured",
    }})
    try:
        while True:
            event = await websocket.receive_json()
            kind = event.get("event") if isinstance(event, dict) else None
            payload = event.get("payload", {}) if isinstance(event, dict) else {}
            if not isinstance(payload, dict):
                await websocket.send_json({"event": "error", "payload": {
                    "code": "INVALID_PAYLOAD", "message": "Event payload must be an object."
                }})
                continue
            if kind == "session.start":
                await websocket.send_json({"event": "provider.status", "payload": {
                    "providers": gnani.statuses()
                }})
            elif kind == "audio.chunk":
                encoded = payload.get("data", "")
                if not isinstance(encoded, str) or len(encoded) > settings.max_audio_frame_bytes * 2:
                    await websocket.send_json({"event": "error", "payload": {
                        "code": "FRAME_TOO_LARGE", "message": "Audio frame exceeds configured limit."
                    }})
                    continue
                try:
                    audio = base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError):
                    await websocket.send_json({"event": "error", "payload": {
                        "code": "INVALID_AUDIO", "message": "Audio data must be base64."
                    }})
                    continue
                if len(audio) > settings.max_audio_frame_bytes:
                    await websocket.send_json({"event": "error", "payload": {
                        "code": "FRAME_TOO_LARGE", "message": "Audio frame exceeds configured limit."
                    }})
                    continue
                seq = payload.get("sequence")
                if not isinstance(seq, int) or seq <= session["last_sequence"]:
                    await websocket.send_json({"event": "error", "payload": {
                        "code": "INVALID_SEQUENCE", "message": "Audio sequence must increase."
                    }})
                    continue
                session["last_sequence"] = seq
                await websocket.send_json({"event": "provider.status", "payload": {
                    "provider": "prisma", "status": "not_configured",
                    "detail": "Audio frame received; live Prisma integration is not enabled.",
                }})
            elif kind == "transcript.demo" and session["session_type"] == "scam_demo":
                # This client-supplied event is explicitly a local demo rule test, never a
                # trusted production transcript. Replace it with Prisma-originated text.
                transcript = str(payload.get("text", ""))[:2000]
                result = analyse_explicit_request(transcript)
                if result:
                    await websocket.send_json({"event": "threat.detected", "payload": result.model_dump()})
                else:
                    await websocket.send_json({"event": "transcript.partial", "payload": {
                        "text": transcript, "source": "demo_input"
                    }})
            elif kind == "assistant.interrupt":
                await websocket.send_json({"event": "assistant.interrupted", "payload": {"accepted": True}})
            elif kind == "session.end":
                session["status"] = "ended"
                await websocket.send_json({"event": "session.ended", "payload": {}})
                break
            else:
                await websocket.send_json({"event": "error", "payload": {
                    "code": "UNKNOWN_EVENT", "message": "Unsupported event."
                }})
    except WebSocketDisconnect:
        session["status"] = "disconnected"
    finally:
        if session["status"] != "ended":
            session["status"] = "disconnected"
