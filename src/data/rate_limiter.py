from __future__ import annotations

from collections import deque
from collections.abc import Callable
from threading import Lock
import time

from src.data.quality_collector import QuotaExhausted


class RateLimiter:
    def __init__(
        self,
        *,
        requests_per_minute: int,
        daily_quota: int,
        time_func: Callable[[], float] = time.time,
        sleep_func: Callable[[float], None] = time.sleep,
    ) -> None:
        self.requests_per_minute = requests_per_minute
        self.daily_quota = daily_quota
        self._time = time_func
        self._sleep = sleep_func
        self._minute_window: deque[float] = deque()
        self._daily_count = 0
        self._daily_started_at = self._time()
        self._lock = Lock()

    def acquire(self) -> None:
        with self._lock:
            now = self._time()
            if now - self._daily_started_at >= 86_400:
                self._daily_count = 0
                self._daily_started_at = now

            if self._daily_count >= self.daily_quota:
                raise QuotaExhausted("DART daily quota reached")

            while self._minute_window and now - self._minute_window[0] >= 60:
                self._minute_window.popleft()

            if len(self._minute_window) >= self.requests_per_minute:
                sleep_for = 60 - (now - self._minute_window[0])
                self._sleep(max(sleep_for, 0))
                now = self._time()
                while self._minute_window and now - self._minute_window[0] >= 60:
                    self._minute_window.popleft()

            self._minute_window.append(now)
            self._daily_count += 1
