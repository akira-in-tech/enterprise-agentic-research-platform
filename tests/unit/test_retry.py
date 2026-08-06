from collections.abc import Callable

import pytest

from app.core.retry import call_with_backoff


class FakeSleep:
    """Record delays without actually sleeping, for deterministic tests."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def fixed_jitter(value: float) -> Callable[[], float]:
    def jitter() -> float:
        return value

    return jitter


class FlakyCall:
    """Fail a fixed number of times, then succeed."""

    def __init__(
        self,
        *,
        failures: int,
        error: Exception,
        result: str = "ok",
    ) -> None:
        self.failures = failures
        self.error = error
        self.result = result
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1

        if self.calls <= self.failures:
            raise self.error

        return self.result


@pytest.mark.anyio
async def test_rejects_invalid_configuration() -> None:
    async def noop() -> None:
        return None

    with pytest.raises(ValueError, match="max_attempts"):
        await call_with_backoff(noop, retryable=(RuntimeError,), max_attempts=0)

    with pytest.raises(ValueError, match="base_delay_seconds"):
        await call_with_backoff(noop, retryable=(RuntimeError,), base_delay_seconds=0)

    with pytest.raises(ValueError, match="max_delay_seconds"):
        await call_with_backoff(
            noop,
            retryable=(RuntimeError,),
            base_delay_seconds=1.0,
            max_delay_seconds=0.5,
        )


@pytest.mark.anyio
async def test_succeeds_on_first_attempt_without_sleeping() -> None:
    sleep = FakeSleep()
    call = FlakyCall(failures=0, error=RuntimeError("unused"))

    result = await call_with_backoff(
        call,
        retryable=(RuntimeError,),
        sleep=sleep,
    )

    assert result == "ok"
    assert call.calls == 1
    assert sleep.delays == []


@pytest.mark.anyio
async def test_retries_a_retryable_error_until_it_succeeds() -> None:
    sleep = FakeSleep()
    call = FlakyCall(failures=2, error=RuntimeError("transient"))

    result = await call_with_backoff(
        call,
        retryable=(RuntimeError,),
        max_attempts=3,
        base_delay_seconds=0.25,
        max_delay_seconds=4.0,
        sleep=sleep,
        jitter=fixed_jitter(1.0),
    )

    assert result == "ok"
    assert call.calls == 3
    # Full jitter with jitter()==1.0: delay == min(max_delay, base * 2**(attempt-1)).
    assert sleep.delays == [0.25, 0.5]


@pytest.mark.anyio
async def test_caps_the_delay_at_max_delay_seconds() -> None:
    sleep = FakeSleep()
    call = FlakyCall(failures=4, error=RuntimeError("transient"))

    result = await call_with_backoff(
        call,
        retryable=(RuntimeError,),
        max_attempts=5,
        base_delay_seconds=1.0,
        max_delay_seconds=2.0,
        sleep=sleep,
        jitter=fixed_jitter(1.0),
    )

    assert result == "ok"
    # Uncapped would be 1, 2, 4, 8 -- capped at max_delay_seconds=2.0.
    assert sleep.delays == [1.0, 2.0, 2.0, 2.0]


@pytest.mark.anyio
async def test_scales_the_delay_by_the_jitter_fraction() -> None:
    sleep = FakeSleep()
    call = FlakyCall(failures=1, error=RuntimeError("transient"))

    await call_with_backoff(
        call,
        retryable=(RuntimeError,),
        base_delay_seconds=1.0,
        max_delay_seconds=10.0,
        sleep=sleep,
        jitter=fixed_jitter(0.5),
    )

    assert sleep.delays == [0.5]


@pytest.mark.anyio
async def test_raises_the_last_error_after_exhausting_attempts() -> None:
    sleep = FakeSleep()
    call = FlakyCall(failures=5, error=RuntimeError("still failing"))

    with pytest.raises(RuntimeError, match="still failing"):
        await call_with_backoff(
            call,
            retryable=(RuntimeError,),
            max_attempts=3,
            sleep=sleep,
            jitter=fixed_jitter(1.0),
        )

    assert call.calls == 3
    assert len(sleep.delays) == 2


@pytest.mark.anyio
async def test_does_not_retry_a_non_retryable_exception() -> None:
    sleep = FakeSleep()
    call = FlakyCall(failures=1, error=ValueError("not transient"))

    with pytest.raises(ValueError, match="not transient"):
        await call_with_backoff(
            call,
            retryable=(RuntimeError,),
            sleep=sleep,
        )

    assert call.calls == 1
    assert sleep.delays == []
