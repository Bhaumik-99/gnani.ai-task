import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int = 60, max_keys: int = 10_000):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        events = self._events[key]
        cutoff = now - self.window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(now)
        if len(self._events) > self.max_keys:
            stale = [candidate for candidate, stamps in self._events.items() if not stamps or stamps[-1] <= cutoff]
            for candidate in stale:
                self._events.pop(candidate, None)
                if len(self._events) <= self.max_keys:
                    break
            while len(self._events) > self.max_keys:
                self._events.pop(next(iter(self._events)))
        return True
