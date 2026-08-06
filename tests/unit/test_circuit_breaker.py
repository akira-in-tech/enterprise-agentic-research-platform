import pytest

from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)


class FakeClock:
    """Provide a controllable monotonic clock for deterministic tests."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


async def fail() -> None:
    raise RuntimeError("boom")


async def succeed() -> str:
    return "ok"


def test_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="failure_threshold"):
        CircuitBreaker(failure_threshold=0)

    with pytest.raises(ValueError, match="reset_timeout_seconds"):
        CircuitBreaker(reset_timeout_seconds=0)


@pytest.mark.anyio
async def test_stays_closed_below_the_failure_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout_seconds=10)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(fail)

    assert breaker.state is CircuitState.CLOSED


@pytest.mark.anyio
async def test_opens_after_consecutive_failures_reach_the_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=10)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(fail)

    assert breaker.state is CircuitState.OPEN


@pytest.mark.anyio
async def test_open_circuit_rejects_calls_without_invoking_the_function() -> None:
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=10)

    with pytest.raises(RuntimeError):
        await breaker.call(fail)

    calls = 0

    async def tracked() -> None:
        nonlocal calls
        calls += 1

    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(tracked)

    assert calls == 0


@pytest.mark.anyio
async def test_success_resets_the_failure_count() -> None:
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_seconds=10)

    with pytest.raises(RuntimeError):
        await breaker.call(fail)

    assert await breaker.call(succeed) == "ok"
    assert breaker.state is CircuitState.CLOSED

    with pytest.raises(RuntimeError):
        await breaker.call(fail)

    # Still closed: the prior failure was reset by the intervening success,
    # so this is only the first failure toward a fresh threshold of two.
    assert breaker.state is CircuitState.CLOSED


@pytest.mark.anyio
async def test_half_open_trial_after_the_reset_timeout_can_close_the_circuit() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=30, clock=clock)

    with pytest.raises(RuntimeError):
        await breaker.call(fail)
    state_after_failure = breaker.state
    assert state_after_failure is CircuitState.OPEN

    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(succeed)

    clock.advance(30)

    assert await breaker.call(succeed) == "ok"
    state_after_success = breaker.state
    assert state_after_success is CircuitState.CLOSED


@pytest.mark.anyio
async def test_half_open_trial_failure_reopens_the_circuit() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_seconds=30, clock=clock)

    with pytest.raises(RuntimeError):
        await breaker.call(fail)

    clock.advance(30)

    with pytest.raises(RuntimeError):
        await breaker.call(fail)

    assert breaker.state is CircuitState.OPEN

    with pytest.raises(CircuitBreakerOpenError):
        await breaker.call(succeed)
