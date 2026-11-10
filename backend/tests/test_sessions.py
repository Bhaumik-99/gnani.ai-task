import asyncio

from app.sessions.rate_limit import SlidingWindowLimiter, normalize_client_ip
from app.sessions.store import _RELEASE_LEASE_LUA, _SLIDING_RATE_LIMIT_LUA, SessionStore
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


def test_in_memory_claim_expires_and_checks_ownership(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.sessions.store.time.monotonic", lambda: clock[0])

    async def run():
        store = SessionStore(ttl_seconds=10)
        await store.set("s1", {"session_id": "s1"})
        assert await store.claim("s1", owner="owner-a")
        assert not await store.release("s1", owner="owner-b")
        clock[0] += 5
        await store.set("s1", {"session_id": "s1"})
        clock[0] += 6
        assert await store.claim("s1", owner="owner-b")
        assert not await store.release("s1", owner="owner-a")
        assert await store.release("s1", owner="owner-b")

    asyncio.run(run())


def test_redis_ownership_release_and_sliding_window(monkeypatch):
    wall_clock = [1_700_000_059.0]
    monkeypatch.setattr("app.sessions.store.time.time", lambda: wall_clock[0])

    class FakeRedis:
        def __init__(self):
            self.kv = {}
            self.zsets = {}

        async def set(self, key, value, ex=None, nx=False):
            if nx and key in self.kv:
                return False
            self.kv[key] = value
            return True

        async def delete(self, *keys):
            removed = 0
            for key in keys:
                if key in self.kv:
                    self.kv.pop(key)
                    removed += 1
            return removed

        async def eval(self, script, _numkeys, *args):
            if script == _RELEASE_LEASE_LUA:
                key, owner = args
                if self.kv.get(key) == owner:
                    self.kv.pop(key, None)
                    return 1
                return 0
            if script == _SLIDING_RATE_LIMIT_LUA:
                key, now_ms, cutoff_ms, limit, _ttl, member = args
                entries = self.zsets.setdefault(key, [])
                entries[:] = [(score, val) for score, val in entries if score > int(cutoff_ms)]
                if len(entries) >= int(limit):
                    return 0
                entries.append((int(now_ms), member))
                return 1
            raise AssertionError("Unexpected Lua script")

    async def run():
        store = SessionStore(ttl_seconds=60)
        store._redis = FakeRedis()
        assert await store.claim("s1", owner="owner-a")
        assert not await store.release("s1", owner="owner-b")
        assert await store.release("s1", owner="owner-a")

        assert await store.allow_rate_limit("198.51.100.1", limit=2, window_seconds=60)
        assert await store.allow_rate_limit("198.51.100.1", limit=2, window_seconds=60)
        wall_clock[0] += 2.0  # Crosses a minute boundary, still inside 60s sliding window.
        assert not await store.allow_rate_limit("198.51.100.1", limit=2, window_seconds=60)
        wall_clock[0] += 60.0
        assert await store.allow_rate_limit("198.51.100.1", limit=2, window_seconds=60)

    asyncio.run(run())


def test_normalize_client_ip_handles_ipv6_and_mapped_ipv4():
    assert normalize_client_ip(None) == "unknown"
    assert normalize_client_ip("::ffff:127.0.0.1") == "127.0.0.1"
    assert normalize_client_ip("2001:db8:1:2::1") == normalize_client_ip("2001:db8:1:2::dead:beef")
