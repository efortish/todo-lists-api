import pytest

from app.infrastructure.rate_limit import RateLimiter

pytestmark = pytest.mark.unit


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_sliding_window():
    clock = FakeClock()
    limiter = RateLimiter(limit=2, window_seconds=60, clock=clock)

    assert limiter.hit("ip") is None
    clock.now += 10
    assert limiter.hit("ip") is None
    assert limiter.hit("ip") == 50  # the first hit frees its slot 50 s from now
    assert limiter.hit("other-ip") is None

    clock.now += 50
    assert limiter.hit("ip") is None


def test_idle_keys_are_forgotten():
    clock = FakeClock()
    limiter = RateLimiter(limit=1, window_seconds=1, clock=clock)
    for i in range(10_001):
        limiter.hit(f"ip-{i}")

    clock.now += 2
    limiter.hit("fresh")

    assert len(limiter._hits) == 1
