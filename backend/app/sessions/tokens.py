import base64
import hashlib
import hmac
import json
import time


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def issue_session_token(session_id: str, secret: str, ttl_seconds: int) -> str:
    payload = {"sid": session_id, "exp": int(time.time()) + ttl_seconds}
    encoded = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = _b64(hmac.new(secret.encode(), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def verify_session_token(token: str, session_id: str, secret: str) -> bool:
    try:
        encoded, signature = token.split(".", 1)
        expected = _b64(hmac.new(secret.encode(), encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return False
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        return payload.get("sid") == session_id and int(payload.get("exp", 0)) > int(time.time())
    except (ValueError, TypeError, json.JSONDecodeError):
        return False
