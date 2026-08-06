import asyncio
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TypeVar

ResultT = TypeVar("ResultT")


class CircuitState(StrEnum):
    """Represent the classic three-state circuit-breaker machine."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(RuntimeError):
    """Raised when a call is rejected because the circuit is open."""


class CircuitBreaker:
    """Stop calling a failing external dependency until it recovers.

    Closed: calls pass through normally; consecutive failures are counted.
    Open: calls fail immediately with CircuitBreakerOpenError, without
      reaching the dependency, until reset_timeout_seconds has elapsed
      since the circuit opened.
    Half-open: exactly one trial call is allowed through once the reset
      timeout elapses; success closes the circuit, failure reopens it and
      restarts the timeout.

    This guards a dependency from being hammered with doomed requests once
    it is clearly failing, complementing (not replacing) per-call retries
    and timeouts.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        reset_timeout_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1.")

        if reset_timeout_seconds <= 0:
            raise ValueError("reset_timeout_seconds must be greater than 0.")

        self._failure_threshold = failure_threshold
        self._reset_timeout_seconds = reset_timeout_seconds
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._half_open_trial_in_flight = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Return the breaker's current state."""

        return self._state

    async def call(self, func: Callable[[], Awaitable[ResultT]]) -> ResultT:
        """Run func, tracking it toward the circuit's open/closed decision."""

        await self._before_call()

        try:
            result = await func()
        except Exception:
            await self._on_failure()
            raise
        else:
            await self._on_success()
            return result

    async def _before_call(self) -> None:
        async with self._lock:
            if self._state is CircuitState.OPEN:
                assert self._opened_at is not None

                if self._clock() - self._opened_at < self._reset_timeout_seconds:
                    raise CircuitBreakerOpenError(
                        "Circuit breaker is open; the dependency is temporarily unavailable."
                    )

                self._state = CircuitState.HALF_OPEN
                self._half_open_trial_in_flight = True
                return

            if self._state is CircuitState.HALF_OPEN:
                if self._half_open_trial_in_flight:
                    raise CircuitBreakerOpenError(
                        "Circuit breaker is half-open; a trial call is already in flight."
                    )

                self._half_open_trial_in_flight = True

    async def _on_success(self) -> None:
        async with self._lock:
            self._consecutive_failures = 0
            self._state = CircuitState.CLOSED
            self._opened_at = None
            self._half_open_trial_in_flight = False

    async def _on_failure(self) -> None:
        async with self._lock:
            self._half_open_trial_in_flight = False

            if self._state is CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()
                return

            self._consecutive_failures += 1

            if self._consecutive_failures >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()
