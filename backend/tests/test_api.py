import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app


def test_health_and_config_do_not_expose_credentials():
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        config = client.get("/api/config")
        assert config.status_code == 200
        assert "api_key" not in config.text.lower()
        assert "secret" not in config.text.lower()
        assert config.json()["prisma_sample_rate"] in {8000, 16000}


def test_session_returns_signed_capability():
    with TestClient(app) as client:
        response = client.post("/api/sessions", json={"session_type": "scam_demo"})
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] and data["token"]
        assert data["expires_in"] > 0


def test_session_schema_rejects_unknown_values_and_fields():
    with TestClient(app) as client:
        assert client.post("/api/sessions", json={"session_type": "unknown"}).status_code == 422
        assert client.post("/api/sessions", json={"session_type": "scam_demo", "language": "indic-auto"}).status_code == 422
        assert client.post("/api/sessions", json={"session_type": "scam_demo", "extra": True}).status_code == 422


def test_websocket_rejects_invalid_capability():
    with TestClient(app) as client:
        session = client.post("/api/sessions", json={"session_type": "scam_demo"}).json()
        with pytest.raises(WebSocketDisconnect) as disconnected:
            with client.websocket_connect(
                f"/ws/sessions/{session['session_id']}",
                subprotocols=["vaanishield.v1", "session.bad-token"],
                headers={"Origin": "http://localhost:5173"},
            ):
                pass
        assert disconnected.value.code == 4401


def test_websocket_rejects_missing_origin():
    with TestClient(app) as client:
        session = client.post("/api/sessions", json={"session_type": "scam_demo"}).json()
        with pytest.raises(WebSocketDisconnect) as disconnected:
            with client.websocket_connect(
                f"/ws/sessions/{session['session_id']}",
                subprotocols=["vaanishield.v1", f"session.{session['token']}"],
            ):
                pass
        assert disconnected.value.code == 4403


def test_websocket_rejects_untrusted_origin():
    with TestClient(app) as client:
        session = client.post("/api/sessions", json={"session_type": "scam_demo"}).json()
        with pytest.raises(WebSocketDisconnect) as disconnected:
            with client.websocket_connect(
                f"/ws/sessions/{session['session_id']}",
                subprotocols=["vaanishield.v1", f"session.{session['token']}"],
                headers={"Origin": "https://attacker.example"},
            ):
                pass
        assert disconnected.value.code == 4403


def test_websocket_demo_detects_explicit_credential_request():
    with TestClient(app) as client:
        session = client.post("/api/sessions", json={"session_type": "scam_demo"}).json()
        with client.websocket_connect(
            f"/ws/sessions/{session['session_id']}",
            subprotocols=["vaanishield.v1", f"session.{session['token']}"],
            headers={"Origin": "http://localhost:5173"},
        ) as ws:
            assert ws.receive_json()["event"] == "session.ready"
            assert ws.receive_json()["event"] == "provider.status"
            ws.send_json({"event": "transcript.demo", "payload": {"text": "Please share your OTP to unblock your account."}})
            events = []
            for _ in range(4):
                event = ws.receive_json()
                events.append(event["event"])
                if "threat.detected" in events and "transcript.demo_ack" in events:
                    break
            assert "transcript.final" in events
            assert "threat.detected" in events
            assert "transcript.demo_ack" in events


def test_websocket_rejects_malformed_binary_audio():
    with TestClient(app) as client:
        session = client.post("/api/sessions", json={"session_type": "scam_demo"}).json()
        with client.websocket_connect(
            f"/ws/sessions/{session['session_id']}",
            subprotocols=["vaanishield.v1", f"session.{session['token']}"],
            headers={"Origin": "http://localhost:5173"},
        ) as ws:
            assert ws.receive_json()["event"] == "session.ready"
            assert ws.receive_json()["event"] == "provider.status"
            ws.send_bytes(b"invalid")
            assert ws.receive_json()["payload"]["code"] == "INVALID_AUDIO_FRAME"
            ws.send_json({"event": "session.end", "payload": {}})
            assert ws.receive_json()["event"] == "session.ended"


def test_websocket_disallows_second_active_connection():
    with TestClient(app) as client:
        session = client.post("/api/sessions", json={"session_type": "scam_demo"}).json()
        protocols = ["vaanishield.v1", f"session.{session['token']}"]
        headers = {"Origin": "http://localhost:5173"}
        with client.websocket_connect(f"/ws/sessions/{session['session_id']}", subprotocols=protocols, headers=headers) as first:
            assert first.receive_json()["event"] == "session.ready"
            with pytest.raises(WebSocketDisconnect) as disconnected:
                with client.websocket_connect(f"/ws/sessions/{session['session_id']}", subprotocols=protocols, headers=headers):
                    pass
            assert disconnected.value.code == 4409


def test_settings_coerces_string_literal_ints():
    from pydantic import ValidationError

    from app.config import Settings

    settings = Settings(_env_file=None, prisma_sample_rate="8000", timbre_sample_rate="16000", max_audio_frame_bytes="1024")
    assert settings.prisma_sample_rate == 8000
    assert settings.timbre_sample_rate == 16000
    assert settings.max_audio_frame_bytes == 1024
    with pytest.raises(ValidationError):
        Settings(_env_file=None, prisma_sample_rate="44100")


def test_contradictory_evon_output_triggers_uncertain_fallback(monkeypatch):
    async def bad_classify(_transcript, _context):
        return {
            "scam_detected": False,
            "risk_level": "critical",
            "risk_score": 95,
            "recommended_action": "end_call",
            "explanation": "Contradictory output",
        }

    monkeypatch.setattr("app.main.evon.classify_scam", bad_classify)
    with TestClient(app) as client:
        session = client.post("/api/sessions", json={"session_type": "scam_demo"}).json()
        with client.websocket_connect(
            f"/ws/sessions/{session['session_id']}",
            subprotocols=["vaanishield.v1", f"session.{session['token']}"],
            headers={"Origin": "http://localhost:5173"},
        ) as ws:
            assert ws.receive_json()["event"] == "session.ready"
            assert ws.receive_json()["event"] == "provider.status"
            ws.send_json({"event": "transcript.demo", "payload": {"text": "Can you check my recent order?"}})
            received = [ws.receive_json() for _ in range(3)]
            events = [item["event"] for item in received]
            assert "threat.detected" not in events
            status_events = [item for item in received if item["event"] == "analysis.status"]
            assert status_events and status_events[0]["payload"]["mode"] == "uncertain"


def test_split_turn_and_small_llm_scam_escalation(monkeypatch):
    async def small_llm_classify(transcript, _context):
        if "KYC" in transcript:
            return {
                "scam_detected": True,
                "risk_level": "medium",
                "risk_score": 60,
                "scam_type": "financial_scam",
                "signals": ["kyc_phishing_link"],
                "explanation": "Caller asks user to click an urgent KYC update link.",
                "recommended_action": "continue_with_caution",
                "warning_message": "Do not click unknown KYC links.",
            }
        return {
            "scam_detected": False,
            "risk_level": "low",
            "risk_score": 5,
            "scam_type": "none",
            "signals": [],
            "explanation": "Incomplete phrase.",
            "recommended_action": "continue_with_caution",
            "warning_message": "",
        }

    monkeypatch.setattr("app.main.settings.gnani_api_key", "")
    monkeypatch.setattr("app.main.evon.classify_scam", small_llm_classify)
    with TestClient(app) as client:
        session = client.post("/api/sessions", json={"session_type": "scam_demo"}).json()
        with client.websocket_connect(
            f"/ws/sessions/{session['session_id']}",
            subprotocols=["vaanishield.v1", f"session.{session['token']}"],
            headers={"Origin": "http://localhost:5173"},
        ) as ws:
            assert ws.receive_json()["event"] == "session.ready"
            assert ws.receive_json()["event"] == "provider.status"
            ws.send_json({"event": "transcript.demo", "payload": {"text": "Your KYC is pending, click this link now."}})
            received = [ws.receive_json() for _ in range(3)]
            threats = [item for item in received if item["event"] == "threat.detected"]
            assert threats and threats[0]["payload"]["recommended_action"] == "warn_user"

            ws.send_json({"event": "transcript.demo", "payload": {"text": "Apna OTP"}})
            for _ in range(3):
                ws.receive_json()
            ws.send_json({"event": "transcript.demo", "payload": {"text": "bata do"}})
            split_received = [ws.receive_json() for _ in range(3)]
            split_threats = [item for item in split_received if item["event"] == "threat.detected"]
            assert split_threats and split_threats[0]["payload"]["scam_type"] == "otp_harvesting"


def test_assistant_mode_detects_explicit_scam_during_conversation(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock

    from app.main import analyse_turn

    sent = []

    class FakeWS:
        async def send_json(self, data):
            sent.append(data)

        async def send_bytes(self, _chunk):
            pass

    monkeypatch.setattr("app.main.settings.gnani_api_key", "")
    respond_mock = AsyncMock(return_value="should not be called")
    monkeypatch.setattr("app.main.evon.respond", respond_mock)

    asyncio.run(
        analyse_turn(
            "assistant",
            "कृपया अपना ओटीपी बताइए",
            ["कृपया अपना ओटीपी बताइए"],
            [],
            FakeWS(),
            asyncio.Lock(),
            asyncio.Event(),
            set(),
            asyncio.Lock(),
        )
    )
    respond_mock.assert_not_awaited()
    events = [item["event"] for item in sent]
    assert "assistant.message" in events
    assert "threat.detected" in events
