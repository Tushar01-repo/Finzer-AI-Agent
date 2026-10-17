"""Safe, bounded retries for Finzer's read-only and idempotent operations.

This utility does not determine whether an MCP write is safe to replay.
Callers must explicitly opt in only for read-only operations or operations
with a verified, server-enforced idempotency contract.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 0.2
    max_delay_seconds: float = 2.0
    multiplier: float = 2.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.initial_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("delays must be >= 0")
        if self.initial_delay_seconds > self.max_delay_seconds:
            raise ValueError("initial delay must not exceed max delay")
        if self.multiplier < 1:
            raise ValueError("multiplier must be >= 1")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")


class RetryNotAllowedError(ValueError):
    """Raised when the caller has not established retry safety."""


def retry_call(
    operation: Callable[[], T],
    *,
    retry_safe: bool = False,
    policy: RetryPolicy | None = None,
    retryable_exceptions: tuple[type[Exception], ...] = (TimeoutError, ConnectionError),
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> T:
    """Execute a retry-safe operation with bounded exponential backoff.

    ``retry_safe`` must only be True for read-only operations or operations
    whose remote server guarantees idempotency. A local reservation alone
    does not make an ambiguous write safe to retry.

    ``on_retry`` receives (failed_attempt_number, exception, delay_seconds).
    The final failed attempt raises its original exception without sleeping.
    """
    if not retry_safe:
        raise RetryNotAllowedError(
            "Automatic retries require explicit retry_safe=True; "
            "do not retry ambiguous MCP writes"
        )
    config = policy or RetryPolicy()
    if not retryable_exceptions:
        raise ValueError("retryable_exceptions cannot be empty")

    for attempt in range(1, config.max_attempts + 1):
        try:
            return operation()
        except retryable_exceptions as exc:
            if attempt == config.max_attempts:
                raise
            base_delay = min(
                config.max_delay_seconds,
                config.initial_delay_seconds * config.multiplier ** (attempt - 1),
            )
            # Uniform jitter in [base*(1-jitter), base*(1+jitter)].
            bounded_random = min(1.0, max(0.0, random_value()))
            delay = max(0.0, base_delay * (1 + config.jitter_ratio * (2 * bounded_random - 1)))
            delay = min(config.max_delay_seconds, delay)
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            sleep(delay)

    raise AssertionError("unreachable")
