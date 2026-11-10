import ipaddress
import time
from collections import defaultdict, deque


def normalize_client_ip(host: str | None) -> str:
    """Normalize client IPs and aggregate IPv6 addresses to /64 prefixes for rate limiting."""
    if not host:
        return "unknown"
    stripped = host.strip()
    if not stripped:
        return "unknown"
    try:
        addr = ipaddress.ip_address(stripped)
    except ValueError:
        return stripped
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped:
            return str(addr.ipv4_mapped)
        return str(ipaddress.IPv6Network((addr, 64), strict=False))
    return str(addr)


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
