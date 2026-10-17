"""Thread-safe, in-process metrics for the Finzer ReAct agent.

Metrics are process-local and reset on restart. Never use unbounded user IDs,
run IDs, prompts, or tool arguments as metric labels.
"""
from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator

from app.observability.config import get_observability_settings


@dataclass
class _Histogram:
    count: int = 0
    total: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    buckets: dict[float, int] = field(default_factory=dict)


class AgentMetrics:
    """Bounded-label counters and latency histograms for a single process."""

    LATENCY_BUCKETS_MS = (10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0, 10000.0)
    OPERATIONS = frozenset({"agent", "mcp", "rag", "llm", "approval", "checkpoint"})
    OUTCOMES = frozenset({"success", "error", "timeout", "rejected", "pending"})

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counts: dict[tuple[str, str], int] = defaultdict(int)
        self._latencies: dict[str, _Histogram] = {}
        self._input_tokens = 0
        self._output_tokens = 0
        self._estimated_cost_usd = 0.0

    @staticmethod
    def _validate(operation: str, outcome: str | None = None) -> None:
        if operation not in AgentMetrics.OPERATIONS:
            raise ValueError(f"Unknown operation: {operation!r}")
        if outcome is not None and outcome not in AgentMetrics.OUTCOMES:
            raise ValueError(f"Unknown outcome: {outcome!r}")

    @staticmethod
    def _enabled() -> bool:
        return get_observability_settings().metrics_enabled

    def record_operation(self, operation: str, outcome: str = "success") -> None:
        self._validate(operation, outcome)
        if not self._enabled():
            return
        with self._lock:
            self._counts[(operation, outcome)] += 1

    def record_latency(self, operation: str, duration_ms: float) -> None:
        self._validate(operation)
        if not math.isfinite(duration_ms) or duration_ms < 0:
            raise ValueError("duration_ms must be a finite non-negative number")
        if not self._enabled():
            return
        with self._lock:
            hist = self._latencies.setdefault(operation, _Histogram())
            hist.count += 1
            hist.total += duration_ms
            hist.minimum = duration_ms if hist.minimum is None else min(hist.minimum, duration_ms)
            hist.maximum = duration_ms if hist.maximum is None else max(hist.maximum, duration_ms)
            for bound in self.LATENCY_BUCKETS_MS:
                if duration_ms <= bound:
                    hist.buckets[bound] = hist.buckets.get(bound, 0) + 1

    @contextmanager
    def time_operation(self, operation: str) -> Iterator[None]:
        """Time an operation, counting success or error, then re-raise errors."""
        self._validate(operation)
        started = time.perf_counter()
        outcome = "success"
        try:
            yield
        except TimeoutError:
            outcome = "timeout"
            raise
        except Exception:
            outcome = "error"
            raise
        finally:
            self.record_latency(operation, (time.perf_counter() - started) * 1000)
            self.record_operation(operation, outcome)

    def record_llm_usage(
        self,
        *,
        input_tokens: int,
        output_tokens: int,
        input_cost_per_million_usd: float | None = None,
        output_cost_per_million_usd: float | None = None,
    ) -> None:
        """Record token usage; calculate cost only if explicit rates are supplied."""
        settings = get_observability_settings()
        if not isinstance(input_tokens, int) or isinstance(input_tokens, bool) or input_tokens < 0:
            raise ValueError("input_tokens must be a non-negative integer")
        if not isinstance(output_tokens, int) or isinstance(output_tokens, bool) or output_tokens < 0:
            raise ValueError("output_tokens must be a non-negative integer")
        for rate in (input_cost_per_million_usd, output_cost_per_million_usd):
            if rate is not None and (not math.isfinite(rate) or rate < 0):
                raise ValueError("Cost rates must be finite and non-negative")
        if not settings.metrics_enabled:
            return
        with self._lock:
            if settings.capture_token_usage:
                self._input_tokens += input_tokens
                self._output_tokens += output_tokens
            if settings.capture_cost_estimates:
                self._estimated_cost_usd += (
                    input_tokens * (input_cost_per_million_usd or 0.0)
                    + output_tokens * (output_cost_per_million_usd or 0.0)
                ) / 1_000_000

    def snapshot(self) -> dict:
        """Return a detached, JSON-serializable snapshot."""
        with self._lock:
            return {
                "operations": {
                    op: {outcome: count for (name, outcome), count in sorted(self._counts.items()) if name == op}
                    for op in sorted({name for name, _ in self._counts})
                },
                "latency_ms": {
                    op: {
                        "count": hist.count,
                        "total": round(hist.total, 3),
                        "avg": round(hist.total / hist.count, 3),
                        "min": round(hist.minimum, 3) if hist.minimum is not None else None,
                        "max": round(hist.maximum, 3) if hist.maximum is not None else None,
                        "buckets_le": {str(bound): hist.buckets.get(bound, 0) for bound in self.LATENCY_BUCKETS_MS},
                        "above_max_bucket": hist.count - hist.buckets.get(self.LATENCY_BUCKETS_MS[-1], 0),
                    }
                    for op, hist in sorted(self._latencies.items())
                },
                "llm_usage": {
                    "input_tokens": self._input_tokens,
                    "output_tokens": self._output_tokens,
                    "estimated_cost_usd": round(self._estimated_cost_usd, 8),
                },
            }

    def reset(self) -> None:
        """Clear in-memory measurements (primarily for tests)."""
        with self._lock:
            self._counts.clear()
            self._latencies.clear()
            self._input_tokens = 0
            self._output_tokens = 0
            self._estimated_cost_usd = 0.0


metrics = AgentMetrics()
