import pytest

from src.data.quality_collector import QuotaExhausted
from src.data.rate_limiter import RateLimiter


class FakeClock:
    def __init__(self, now=1000.0):
        self.now = now
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_rate_limiter_allows_under_minute_limit_without_sleep():
    clock = FakeClock()
    limiter = RateLimiter(
        requests_per_minute=3,
        daily_quota=10,
        time_func=clock.time,
        sleep_func=clock.sleep,
    )

    limiter.acquire()
    limiter.acquire()
    limiter.acquire()

    assert clock.sleeps == []


def test_rate_limiter_sleeps_when_minute_window_is_full():
    clock = FakeClock()
    limiter = RateLimiter(
        requests_per_minute=2,
        daily_quota=10,
        time_func=clock.time,
        sleep_func=clock.sleep,
    )

    limiter.acquire()
    limiter.acquire()
    limiter.acquire()

    assert len(clock.sleeps) == 1
    assert clock.sleeps[0] == pytest.approx(60.0)


def test_rate_limiter_raises_quota_exhausted_after_daily_limit():
    clock = FakeClock()
    limiter = RateLimiter(
        requests_per_minute=10,
        daily_quota=2,
        time_func=clock.time,
        sleep_func=clock.sleep,
    )

    limiter.acquire()
    limiter.acquire()
    with pytest.raises(QuotaExhausted, match="DART daily quota reached"):
        limiter.acquire()


def test_rate_limiter_resets_daily_counter_after_24_hours():
    clock = FakeClock()
    limiter = RateLimiter(
        requests_per_minute=10,
        daily_quota=1,
        time_func=clock.time,
        sleep_func=clock.sleep,
    )

    limiter.acquire()
    clock.now += 86_401
    limiter.acquire()

    assert clock.sleeps == []
