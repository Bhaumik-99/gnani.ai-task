import asyncio
import time

from app.sessions.rate_limit import SlidingWindowLimiter
from app.sessions.store import SessionStore
from app.sessions.tokens import issue_session_token, verify_session_token


def test_signed_session_token_is_bound_to_id_and_secret():
    token = issue_session_token("session-1", "test-secret", 60)
    assert verify_session_token(token, "session-1", "test-secret")
    assert not verify_session_token(token, "session-2", "test-secret")
    assert not verify_session_token(token, "session-1", "wrong-secret")


def test_malformed_session_token_is_rejected():
    assert not verify_session_token("not-a-token", "session-1", "test-secret")


def test_session_expiry_is_enforced(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.sessions.store.time.monotonic", lambda: clock[0])

    async def run():
        store = SessionStore(ttl_seconds=10)
        await store.set("s1", {"session_id": "s1"})
        assert await store.get("s1") is not None
        clock[0] += 11
        assert await store.get("s1") is None

    asyncio.run(run())


def test_only_one_socket_can_claim_a_session():
    async def run():
        store = SessionStore(ttl_seconds=60)
        await store.set("s1", {"session_id": "s1"})
        assert await store.claim("s1")
        assert not await store.claim("s1")
        await store.release("s1")
        assert await store.claim("s1")
        await store.delete("s1")
        assert await store.get("s1") is None

    asyncio.run(run())


def test_sliding_window_limiter_enforces_window(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.sessions.rate_limit.time.monotonic", lambda: clock[0])
    limiter = SlidingWindowLimiter(2, 60)
    assert limiter.allow("client")
    assert limiter.allow("client")
    assert not limiter.allow("client")
    clock[0] += 61
    assert limiter.allow("client")


def test_sliding_window_limiter_bounds_key_count():
    limiter = SlidingWindowLimiter(2, 60, max_keys=3)
    for index in range(20):
        limiter.allow(f"client-{index}")
    assert len(limiter._events) <= 3
