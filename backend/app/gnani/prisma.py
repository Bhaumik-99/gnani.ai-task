import asyncio
import json
from collections.abc import AsyncIterator

from websockets.asyncio.client import ClientConnection, connect as websocket_connect

from app.config import Settings


class PrismaNotConfigured(RuntimeError):
    pass


class PrismaStream:
    """Prisma realtime STT using the published raw mono PCM16LE WebSocket protocol."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.connection: ClientConnection | None = None

    async def connect(self, language_code: str | None = None) -> dict:
        if not self.settings.gnani_api_key:
            raise PrismaNotConfigured("GNANI_API_KEY is not configured")
        headers = {
            "x-api-key-id": self.settings.gnani_api_key,
            "lang_code": language_code or self.settings.prisma_language_code,
            "x-format": self.settings.prisma_format,
            "x-sample-rate": str(self.settings.prisma_sample_rate),
        }
        self.connection = await websocket_connect(
            self.settings.prisma_ws_url, additional_headers=headers,
            open_timeout=10, ping_interval=20, ping_timeout=20,
            max_size=1_048_576, close_timeout=3,
        )
        try:
            raw = await asyncio.wait_for(self.connection.recv(), timeout=10)
            if not isinstance(raw, str):
                raise RuntimeError("Prisma returned an invalid handshake")
            event = json.loads(raw)
            if not isinstance(event, dict):
                raise RuntimeError("Prisma handshake must be a JSON object")
            if event.get("type") == "error":
                raise RuntimeError(str(event.get("message", "Prisma connection failed")))
            if event.get("type") != "connected":
                raise RuntimeError("Prisma did not return the connected event")
            config = event.get("config") or {}
            if config and config.get("sample_rate") != self.settings.prisma_sample_rate:
                raise RuntimeError("Prisma sample rate does not match the configured input rate")
            return event
        except Exception:
            await self.close()
            raise

    async def send_audio(self, frame: bytes) -> None:
        if self.connection is None:
            raise RuntimeError("Prisma is not connected")
        if len(frame) != 1024:
            raise ValueError("Prisma frames must be exactly 1,024 bytes (512 PCM16 samples)")
        await self.connection.send(frame)

    async def events(self) -> AsyncIterator[dict]:
        if self.connection is None:
            return
        async for raw in self.connection:
            if not isinstance(raw, str):
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as error:
                raise RuntimeError("Prisma sent malformed JSON") from error
            if not isinstance(event, dict):
                raise RuntimeError("Prisma event must be a JSON object")
            yield event

    async def close(self) -> None:
        connection = self.connection
        self.connection = None
        if connection is not None:
            await connection.close()
