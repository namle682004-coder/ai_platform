"""
AIP Exponential Backoff and Retry Policies.
Provides jittered exponential backoff and error handling for asynchronous worker pipelines.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Callable, Coroutine, Optional, Tuple, Type

logger = logging.getLogger("aip-dispatcher.retry")


def compute_backoff_delay(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
) -> float:
    """
    Computes exponential backoff delay with full jitter.
    Formula: Delay = uniform(0, min(max_delay, base_delay * 2^attempt))
    """
    exp_delay = min(max_delay, base_delay * (2 ** max(0, attempt - 1)))
    if jitter:
        return random.uniform(0.5 * exp_delay, exp_delay)
    return exp_delay


class RetryPolicy:
    """Configurable retry policy with retry limits and backoff parameters."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.retryable_exceptions = retryable_exceptions


async def execute_with_retry(
    coro_func: Callable[..., Coroutine[Any, Any, Any]],
    *args: Any,
    policy: Optional[RetryPolicy] = None,
    **kwargs: Any,
) -> Any:
    """
    Executes an async callable with automatic jittered exponential backoff.
    """
    p = policy or RetryPolicy()
    last_exc: Optional[Exception] = None

    for attempt in range(1, p.max_retries + 1):
        try:
            return await coro_func(*args, **kwargs)
        except p.retryable_exceptions as exc:
            last_exc = exc
            if attempt >= p.max_retries:
                logger.warning(
                    "Exhausted all %d retries for %s. Error: %s",
                    p.max_retries, coro_func.__name__, exc
                )
                raise
            delay = compute_backoff_delay(attempt, p.base_delay, p.max_delay)
            logger.info(
                "Attempt %d/%d failed with %s. Retrying in %.2fs...",
                attempt, p.max_retries, exc, delay
            )
            await asyncio.sleep(delay)

    raise last_exc or RuntimeError("Execution failed without explicit exception")
