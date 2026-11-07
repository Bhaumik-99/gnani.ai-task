import asyncio
import base64
import json

import pytest

from app.gnani.prisma import PrismaStream
from app.gnani.timbre import TimbreStreamer
from app.risk.evon import EvonClient, extract_json


class FakeSocket:
    def __init__(self, first=None, messages=None):
        self.first = first
        self.messages = list(messages or [])
        self.sent = []
        self.closed = False

    async def recv(self):
        return self.first

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        self.closed = True

    def __aiter__(self):
        self._iterator = iter(self.messages)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeConnect:
    def __init__(self, socket):
        self.socket = socket
        self.kwargs = None

    async def __call__(self, url, **kwargs):
        self.kwargs = {"url": url, **kwargs}
        return self.socket


@pytest.mark.asyncio
async def test_prisma_uses_documented_header_names_and_binary_frames(monkeypatch):
    from app.config import Settings

    socket = FakeSocket(first=json.dumps({"type": "connected", "config": {"sample_rate": 16000, "chunk_size": 512}}))
    connect = FakeConnect(socket)
    monkeypatch.setattr("app.gnani.prisma.websocket_connect", connect)
    settings = Settings(gnani_api_key="test-key")
    stream = PrismaStream(settings)
    await stream.connect("hi-IN")
    headers = connect.kwargs["additional_headers"]
    assert headers["x-api-key-id"] == "test-key"
    assert headers["lang_code"] == "hi-IN"
    assert headers["x-format"] == "transcribe"
    assert headers["x-sample-rate"] == "16000"
    assert "language_code" not in headers
    assert "model" not in headers
    await stream.send_audio(b"\x00" * 1024)
    assert socket.sent == [b"\x00" * 1024]
    with pytest.raises(ValueError):
        await stream.send_audio(b"\x00" * 1023)
    await stream.close()
    assert socket.closed


@pytest.mark.asyncio
async def test_prisma_rejects_bad_handshake_and_closes_socket(monkeypatch):
    from app.config import Settings

    socket = FakeSocket(first=json.dumps({"type": "error", "message": "invalid key"}))
    monkeypatch.setattr("app.gnani.prisma.websocket_connect", FakeConnect(socket))
    stream = PrismaStream(Settings(gnani_api_key="test-key"))
    with pytest.raises(RuntimeError, match="invalid key"):
        await stream.connect()
    assert socket.closed


@pytest.mark.asyncio
async def test_timbre_sends_current_model_request_and_forwards_raw_pcm(monkeypatch):
    from app.config import Settings

    audio = b"\x01\x00\x02\x00"
    socket = FakeSocket(messages=[
        json.dumps({"type": "start"}),
        json.dumps({"type": "audio", "data": {"audio": base64.b64encode(audio).decode(), "is_final": False}}),
        json.dumps({"type": "complete", "data": {"audio": "", "is_final": True}}),
    ])

    class ContextManager:
        async def __aenter__(self):
            return socket

        async def __aexit__(self, *_args):
            return False

    capture = {}
    def connect(url, **kwargs):
        capture.update({"url": url, **kwargs})
        return ContextManager()

    monkeypatch.setattr("app.gnani.timbre.websocket_connect", connect)
    settings = Settings(gnani_api_key="test-key")
    streamer = TimbreStreamer(settings)
    audio_chunks = []
    events = []

    async def save_audio(chunk):
        audio_chunks.append(chunk)

    async def save_event(event):
        events.append(event)

    await streamer.synthesize("नमस्ते", save_audio, save_event, asyncio.Event())
    assert capture["url"] == settings.timbre_ws_url
    assert capture["additional_headers"]["X-API-Key-ID"] == "test-key"
    request = json.loads(socket.sent[0])
    assert request["model"] == "timbre-v2.5"
    assert request["voice"] == "Nalini"
    assert request["language"] == "hi-en"
    assert request["audio_config"]["encoding"] == "linear_pcm"
    assert request["audio_config"]["container"] == "raw"
    assert audio_chunks == [audio]
    assert [event["event"] for event in events] == ["audio.output.start", "audio.output.end"]


def test_evon_json_parser_rejects_non_object_or_invalid_content():
    assert extract_json('prefix {"scam_detected":true}') == {"scam_detected": True}
    assert extract_json("[1,2]") is None
    assert extract_json("not-json") is None


@pytest.mark.asyncio
async def test_evon_uses_self_hosted_openai_compatible_endpoint(monkeypatch):
    from app.config import Settings

    capture = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"scam_detected":false}'}}]}

    class FakeHttpClient:
        def __init__(self, timeout):
            capture["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, headers, json):
            capture.update({"url": url, "headers": headers, "payload": json})
            return FakeResponse()

    monkeypatch.setattr("app.risk.evon.httpx.AsyncClient", FakeHttpClient)
    settings = Settings(evon_base_url="https://evon.internal/v1", evon_api_key="local-secret", evon_model="evon")
    result = await EvonClient(settings).complete([{"role": "user", "content": "hello"}])
    assert result == '{"scam_detected":false}'
    assert capture["url"] == "https://evon.internal/v1/chat/completions"
    assert capture["headers"]["Authorization"] == "Bearer local-secret"
    assert capture["payload"]["model"] == "evon"
    assert capture["payload"]["chat_template_kwargs"]["enable_thinking"] is False
