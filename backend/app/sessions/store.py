import hashlib
import json
import time
from typing import Any
from uuid import uuid4

from app.sessions.rate_limit import SlidingWindowLimiter

_RELEASE_LEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""

_SLIDING_RATE_LIMIT_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local cutoff = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])
local member = ARGV[5]

redis.call("ZREMRANGEBYSCORE", key, "-inf", cutoff)
local count = redis.call("ZCARD", key)
if count >= limit then
    redis.call("EXPIRE", key, ttl)
    return 0
end
redis.call("ZADD", key, now, member)
redis.call("EXPIRE", key, ttl)
return 1
"""


class SessionStore:
    """TTL session store with Redis-backed cross-worker sliding-window rate limiting and lease claims."""

    def __init__(self, redis_url: str = "", ttl_seconds: int = 840):
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self._redis = None
        self._memory: dict[str, tuple[float, dict[str, Any]]] = {}
        self._claims: dict[str, tuple[float, str]] = {}
        self._limiter = SlidingWindowLimiter(10)

    def _purge_expired_claims(self, now: float) -> None:
        expired = [key for key, (expiry, _) in self._claims.items() if expiry <= now]
        for key in expired:
            self._claims.pop(key, None)

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    async def start(self) -> None:
        if not self.redis_url:
            return
        from redis.asyncio import Redis
        self._redis = Redis.from_url(self.redis_url, decode_responses=True, socket_connect_timeout=3)
        await self._redis.ping()

    async def ping(self) -> bool:
        if self._redis is None:
            return not self.redis_url
        await self._redis.ping()
        return True

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def set(self, session_id: str, value: dict[str, Any]) -> None:
        if self._redis is not None:
            await self._redis.setex(f"vaanishield:session:{session_id}", self.ttl_seconds, json.dumps(value))
            return
        now = time.monotonic()
        self._memory[session_id] = (now + self.ttl_seconds, value)
        if len(self._memory) > 10_000:
            for key in [k for k, (expiry, _) in self._memory.items() if expiry <= now]:
                self._memory.pop(key, None)
                self._claims.pop(key, None)
            self._purge_expired_claims(now)
            while len(self._memory) > 10_000:
                oldest = next(iter(self._memory))
                self._memory.pop(oldest)
                self._claims.pop(oldest, None)

    async def get(self, session_id: str) -> dict[str, Any] | None:
        if self._redis is not None:
            raw = await self._redis.get(f"vaanishield:session:{session_id}")
            return json.loads(raw) if raw else None
        item = self._memory.get(session_id)
        if item is None:
            return None
        expiry, value = item
        if expiry <= time.monotonic():
            self._memory.pop(session_id, None)
            self._claims.pop(session_id, None)
            return None
        return value

    async def delete(self, session_id: str) -> None:
        if self._redis is not None:
            await self._redis.delete(f"vaanishield:session:{session_id}", f"vaanishield:active:{session_id}")
        else:
            self._memory.pop(session_id, None)
            self._claims.pop(session_id, None)

    async def claim(self, session_id: str, owner: str | None = None) -> bool:
        lease_owner = owner or "default"
        if self._redis is not None:
            return bool(await self._redis.set(f"vaanishield:active:{session_id}", lease_owner, ex=self.ttl_seconds, nx=True))
        now = time.monotonic()
        session_entry = self._memory.get(session_id)
        if session_entry is not None and session_entry[0] <= now:
            self._memory.pop(session_id, None)
            self._claims.pop(session_id, None)
            return False
        existing = self._claims.get(session_id)
        if existing is not None:
            if existing[0] > now:
                return False
            self._claims.pop(session_id, None)
        if len(self._claims) > 10_000:
            self._purge_expired_claims(now)
            while len(self._claims) > 10_000:
                self._claims.pop(next(iter(self._claims)))
        expiry = min(session_entry[0], now + self.ttl_seconds) if session_entry is not None else now + self.ttl_seconds
        self._claims[session_id] = (expiry, lease_owner)
        return True

    async def release(self, session_id: str, owner: str | None = None) -> bool:
        if self._redis is not None:
            redis_key = f"vaanishield:active:{session_id}"
            if owner is None:
                return bool(await self._redis.delete(redis_key))
            return bool(await self._redis.eval(_RELEASE_LEASE_LUA, 1, redis_key, owner))
        now = time.monotonic()
        existing = self._claims.get(session_id)
        if existing is None:
            return False
        if existing[0] <= now:
            self._claims.pop(session_id, None)
            return False
        if owner is not None and existing[1] != owner:
            return False
        self._claims.pop(session_id, None)
        return True

    async def allow_rate_limit(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        if self._redis is not None:
            now_ms = int(time.time() * 1000)
            cutoff_ms = now_ms - (window_seconds * 1000)
            digest = hashlib.sha256(key.encode()).hexdigest()[:24]
            redis_key = f"vaanishield:rate:{digest}"
            member = f"{now_ms}:{uuid4().hex}"
            allowed = await self._redis.eval(
                _SLIDING_RATE_LIMIT_LUA,
                1,
                redis_key,
                now_ms,
                cutoff_ms,
                limit,
                window_seconds + 2,
                member,
            )
            return bool(int(allowed))
        if self._limiter.limit != limit or self._limiter.window_seconds != window_seconds:
            self._limiter = SlidingWindowLimiter(limit, window_seconds)
        return self._limiter.allow(key)
