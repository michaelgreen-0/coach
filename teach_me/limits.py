"""In-memory sliding-window rate limiting, keyed by arbitrary strings.

Single-process only: run uvicorn with one worker (the default), or the
counters won't be shared.
"""

import threading
import time
from collections import deque

_GC_EVERY = 1000  # calls between sweeps of empty buckets


class RateLimiter:
    def __init__(self, clock=time.monotonic):
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._clock = clock
        self._calls = 0

    def allow(self, key: str, limit: int, window: float) -> bool:
        """Record one event under `key` unless the last `window` seconds
        already hold `limit` of them. Refused events are not recorded, so a
        blocked client doesn't push its own window forward."""
        now = self._clock()
        with self._lock:
            self._calls += 1
            if self._calls % _GC_EVERY == 0:
                self._gc(now)
            q = self._events.setdefault(key, deque())
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def _gc(self, now: float) -> None:
        # drop buckets idle for a day so one-off keys (e.g. IPs) don't pile up
        stale = [k for k, q in self._events.items() if not q or q[-1] <= now - 86400]
        for k in stale:
            del self._events[k]
