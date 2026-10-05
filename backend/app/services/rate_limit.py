"""Small in-process sliding-window limiter. Behind multiple workers use the reverse proxy limiter too."""
import threading
import time
from collections import defaultdict, deque

from app.core.config import get_settings


class SlidingWindow:
    def __init__(self, per_minute_getter):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._limit = per_minute_getter

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self._limit():
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_limiter = SlidingWindow(lambda: get_settings().login_rate_limit_per_minute)
