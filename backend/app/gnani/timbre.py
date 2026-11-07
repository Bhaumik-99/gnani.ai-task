import asyncio
import base64
import json

from websockets.asyncio.client import connect as websocket_connect

from app.config import Settings


class TimbreNotConfigured(RuntimeError):
    pass


class TimbreStreamer:
    """Timbre streaming TTS client; emits raw PCM16LE chunks to the caller."""

    def __init__(self, settings: Settings):
        self.settings = settings

    async def synthesize(self, text: str, send_audio, send_event, cancel_event: asyncio.Event | None = None):
        if not self.settings.gnani_api_key:
            raise TimbreNotConfigured("GNANI_API_KEY is not configured")
        if not text.strip():
            return
        async with websocket_connect(
            self.settings.timbre_ws_url,
            additional_headers={"X-API-Key-ID": self.settings.gnani_api_key},
            open_timeout=10, ping_interval=20, ping_timeout=20,
            max_size=2_097_152, close_timeout=3,
        ) as ws:
            request = {
                "text": text[:1500],
                "voice": self.settings.timbre_voice,
                "model": self.settings.timbre_model,
                "language": self.settings.timbre_language,
                "speed": 1.0,
                "audio_config": {
                    "sample_rate": self.settings.timbre_sample_rate,
                    "num_channels": 1,
                    "sample_width": 2,
                    "encoding": "linear_pcm",
                    "container": "raw",
                },
            }
            await ws.send(json.dumps(request, ensure_ascii=False))
            await send_event({"event": "audio.output.start", "payload": {"sample_rate": self.settings.timbre_sample_rate, "encoding": "pcm_s16le"}})
            total = 0
            completed = False
            async for raw in ws:
                if cancel_event and cancel_event.is_set():
                    break
                if not isinstance(raw, str):
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                kind = event.get("type")
                if kind == "audio":
                    data = event.get("data") or {}
                    encoded = data.get("audio", "") if isinstance(data, dict) else ""
                    if not isinstance(encoded, str) or len(encoded) > 1_400_000:
                        raise RuntimeError("Timbre returned invalid or oversized audio")
                    if encoded:
                        chunk = base64.b64decode(encoded, validate=True)
                        if not chunk or len(chunk) % 2:
                            raise RuntimeError("Timbre returned malformed PCM16 audio")
                        total += len(chunk)
                        if total > self.settings.max_tts_audio_bytes:
                            raise RuntimeError("Timbre output exceeded the per-session audio limit")
                        await send_audio(chunk)
                elif kind == "error":
                    raise RuntimeError(str(event.get("message", "Timbre synthesis failed")))
                elif kind == "complete" or (kind == "audio" and (event.get("data") or {}).get("is_final") is True):
                    completed = True
                    break
            if not completed and not (cancel_event and cancel_event.is_set()):
                raise RuntimeError("Timbre stream ended before the complete event")
            await send_event({"event": "audio.output.end", "payload": {}})
