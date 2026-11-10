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
