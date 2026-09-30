"""In-process sliding-window rate limiter."""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


class RateLimiter:
    """Allow at most ``limit`` hits per ``key`` within ``window_seconds``.

    ponytail: state lives in process memory, so the limit is per worker and resets on
    restart. Move it to Redis (or the reverse proxy) when running several workers.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> float | None:
        """Record a hit. Return ``None`` if allowed, else seconds until the next free slot."""
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                return hits[0] + self._window - now
            hits.append(now)
            if len(self._hits) > 10_000:
                self._forget_idle(now)
            return None

    def _forget_idle(self, now: float) -> None:
        # Bound memory: drop keys whose hits are all outside the window.
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= now - self._window]:
            del self._hits[key]
