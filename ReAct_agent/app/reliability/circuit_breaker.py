"""Thread-safe circuit breaker for Finzer downstream service calls.

Use one CircuitBreaker per downstream dependency. A half-open probe must be
safe to execute; the breaker does not provide write idempotency or retries.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, TypeVar

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Call rejected because the circuit is open or its probe is busy."""


@dataclass(frozen=True)
class CircuitBreakerPolicy:
    failure_threshold: int = 3
    recovery_timeout_seconds: float = 30.0
    success_threshold: int = 1
    counted_exceptions: tuple[type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
    )

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.recovery_timeout_seconds < 0:
            raise ValueError("recovery_timeout_seconds must be >= 0")
        if self.success_threshold < 1:
            raise ValueError("success_threshold must be >= 1")
        if not self.counted_exceptions or not all(
            isinstance(item, type) and issubclass(item, Exception)
            for item in self.counted_exceptions
        ):
            raise ValueError("counted_exceptions must contain exception classes")


class CircuitBreaker:
    """Reject calls after repeated failures; allow one half-open probe."""

    def __init__(
        self,
        policy: CircuitBreakerPolicy | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy or CircuitBreakerPolicy()
        self._clock = clock
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._probe_successes = 0
        self._probe_in_flight = False
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "state": self._state.value,
                "consecutive_failures": self._consecutive_failures,
                "probe_successes": self._probe_successes,
                "probe_in_flight": self._probe_in_flight,
            }

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
        self._probe_in_flight = False
        self._probe_successes = 0

    def _close(self) -> None:
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._probe_successes = 0
        self._probe_in_flight = False
        self._opened_at = None

    def call(self, operation: Callable[..., T], *args: object, **kwargs: object) -> T:
        """Execute one operation, or reject it without invoking it.

        Only configured dependency failures count toward opening the circuit.
        Other exceptions propagate and release any half-open probe slot.
        """
        with self._lock:
            if self._state is CircuitState.OPEN:
                elapsed = self._clock() - (self._opened_at or 0.0)
                if elapsed < self.policy.recovery_timeout_seconds:
                    raise CircuitOpenError("Circuit is open")
                self._state = CircuitState.HALF_OPEN

            is_probe = self._state is CircuitState.HALF_OPEN
            if is_probe:
                if self._probe_in_flight:
                    raise CircuitOpenError("Half-open probe already in progress")
                self._probe_in_flight = True

        try:
            result = operation(*args, **kwargs)
        except Exception as exc:
            with self._lock:
                if is_probe:
                    self._probe_in_flight = False
                if isinstance(exc, self.policy.counted_exceptions):
                    if is_probe:
                        self._open()
                    elif self._state is CircuitState.CLOSED:
                        self._consecutive_failures += 1
                        if self._consecutive_failures >= self.policy.failure_threshold:
                            self._open()
                elif is_probe:
                    # A non-dependency error is not proof of downstream failure.
                    # Keep the circuit half-open and permit another probe.
                    self._probe_successes = 0
            raise
        else:
            with self._lock:
                if is_probe:
                    self._probe_in_flight = False
                    self._probe_successes += 1
                    if self._probe_successes >= self.policy.success_threshold:
                        self._close()
                elif self._state is CircuitState.CLOSED:
                    self._consecutive_failures = 0
            return result
