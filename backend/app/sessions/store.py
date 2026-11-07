import hashlib
import json
import time
from typing import Any

from app.sessions.rate_limit import SlidingWindowLimiter


class SessionStore:
    """TTL session store with Redis-backed cross-worker rate limiting and socket claims."""

    def __init__(self, redis_url: str = "", ttl_seconds: int = 840):
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self._redis = None
        self._memory: dict[str, tuple[float, dict[str, Any]]] = {}
        self._claims: set[str] = set()
        self._limiter = SlidingWindowLimiter(10)

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
        self._memory[session_id] = (time.monotonic() + self.ttl_seconds, value)
        if len(self._memory) > 10_000:
            now = time.monotonic()
            for key in [k for k, (expiry, _) in self._memory.items() if expiry <= now]:
                self._memory.pop(key, None)
            while len(self._memory) > 10_000:
                self._memory.pop(next(iter(self._memory)))

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
            return None
        return value

    async def delete(self, session_id: str) -> None:
        if self._redis is not None:
            await self._redis.delete(f"vaanishield:session:{session_id}", f"vaanishield:active:{session_id}")
        else:
            self._memory.pop(session_id, None)
            self._claims.discard(session_id)

    async def claim(self, session_id: str) -> bool:
        if self._redis is not None:
            return bool(await self._redis.set(f"vaanishield:active:{session_id}", "1", ex=self.ttl_seconds, nx=True))
        if session_id in self._claims:
            return False
        self._claims.add(session_id)
        return True

    async def release(self, session_id: str) -> None:
        if self._redis is not None:
            await self._redis.delete(f"vaanishield:active:{session_id}")
        else:
            self._claims.discard(session_id)

    async def allow_rate_limit(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        if self._redis is not None:
            bucket = int(time.time() // window_seconds)
            digest = hashlib.sha256(key.encode()).hexdigest()[:24]
            redis_key = f"vaanishield:rate:{digest}:{bucket}"
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(redis_key)
                pipe.expire(redis_key, window_seconds + 2)
                count, _ = await pipe.execute()
            return int(count) <= limit
        if self._limiter.limit != limit or self._limiter.window_seconds != window_seconds:
            self._limiter = SlidingWindowLimiter(limit, window_seconds)
        return self._limiter.allow(key)
