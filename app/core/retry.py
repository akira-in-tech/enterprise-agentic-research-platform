import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY_SECONDS = 0.25
DEFAULT_MAX_DELAY_SECONDS = 4.0


async def call_with_backoff[ResultT](
    func: Callable[[], Awaitable[ResultT]],
    *,
    retryable: tuple[type[Exception], ...],
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
    max_delay_seconds: float = DEFAULT_MAX_DELAY_SECONDS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    jitter: Callable[[], float] = random.random,
) -> ResultT:
    """Call func, retrying only `retryable` exceptions with full-jitter backoff.

    Uses the "full jitter" algorithm (sleep = uniform(0, min(max_delay, base *
    2**attempt))), which spreads out retries more effectively than fixed or
    equally-jittered backoff and so is less likely to cause a thundering herd
    against a recovering dependency. Exceptions outside `retryable` (for
    example CircuitBreakerOpenError, or a non-transient validation error)
    propagate immediately on the first attempt.
    """

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1.")

    if base_delay_seconds <= 0:
        raise ValueError("base_delay_seconds must be greater than 0.")

    if max_delay_seconds < base_delay_seconds:
        raise ValueError("max_delay_seconds must be at least base_delay_seconds.")

    attempt = 0

    while True:
        attempt += 1

        try:
            return await func()
        except retryable as error:
            if attempt >= max_attempts:
                raise

            ceiling = min(
                max_delay_seconds,
                base_delay_seconds * (2 ** (attempt - 1)),
            )
            delay = jitter() * ceiling

            logger.warning(
                "Retrying after a transient failure (attempt %s/%s, waiting %.2fs): %s",
                attempt,
                max_attempts,
                delay,
                error,
            )

            await sleep(delay)
