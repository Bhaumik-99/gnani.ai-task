from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_config_does_not_expose_api_key():
    response = client.get("/api/config")
    assert response.status_code == 200
    assert "api_key" not in response.text.lower()


def test_create_demo_session():
    response = client.post("/api/sessions", json={"session_type": "scam_demo", "language": "hi-en"})
    assert response.status_code == 200
    assert response.json()["session_type"] == "scam_demo"
    assert response.json()["session_id"]
