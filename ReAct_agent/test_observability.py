"""Phase 7 observability and reliability checks. Run from ReAct_agent root."""
import json
import logging

import pytest

from app.observability.config import ObservabilitySettings
from app.observability.logger import ContextFilter, StructuredFormatter, log_context
from app.observability.metrics import AgentMetrics
from app.observability.tracing import current_span, trace_span
from app.reliability.retry import RetryNotAllowedError, RetryPolicy, retry_call
from app.reliability.circuit_breaker import (
    CircuitBreaker, CircuitBreakerPolicy, CircuitOpenError, CircuitState,
)
from app.tools.document_rag import DocumentRAGTool
from app.tools.news_rag import NewsRAGTool


def test_observability_settings_defaults():
    settings = ObservabilitySettings(_env_file=None)
    assert settings.service_name
    assert 0 <= settings.tracing_sample_rate <= 1
    assert settings.log_format in ("json", "console")


def test_structured_logging_redacts_secrets():
    record = logging.LogRecord("finzer.test", logging.INFO, __file__, 1,
                               "Authorization: Bearer abc123", (), None)
    record.structured_fields = {
        "api_key": "secret-value",
        "nested": {"access_token": "hidden-value"},
        "safe": "retained",
    }
    with log_context(run_id="test-run", trace_id="test-trace"):
        assert ContextFilter().filter(record)
    payload = json.loads(StructuredFormatter(output_format="json", redact=True).format(record))
    assert payload["run_id"] == "test-run"
    assert payload["trace_id"] == "test-trace"
    assert payload["fields"]["api_key"] == "[REDACTED]"
    assert payload["fields"]["nested"]["access_token"] == "[REDACTED]"
    assert payload["fields"]["safe"] == "retained"
    assert "abc123" not in payload["message"]
    assert "secret-value" not in json.dumps(payload)


def test_log_context_does_not_leak():
    first = logging.LogRecord("finzer.test", logging.INFO, __file__, 1, "test", (), None)
    with log_context(run_id="temporary"):
        ContextFilter().filter(first)
    second = logging.LogRecord("finzer.test", logging.INFO, __file__, 1, "test", (), None)
    ContextFilter().filter(second)
    assert first.run_id == "temporary"
    assert second.run_id is None


def test_nested_trace_parentage_and_reset(monkeypatch):
    monkeypatch.setenv("FINZER_OBS_TRACING_ENABLED", "true")
    from app.observability.config import reset_observability_settings
    reset_observability_settings()
    try:
        assert current_span() is None
        with trace_span("outer") as outer:
            assert outer is not None
            with trace_span("inner") as inner:
                assert inner.trace_id == outer.trace_id
                assert inner.parent_span_id == outer.span_id
                assert current_span() is inner
            assert current_span() is outer
        assert current_span() is None
        assert outer.status == inner.status == "ok"
        assert outer.duration_ms >= 0
    finally:
        reset_observability_settings()


def test_trace_exception_restores_context(monkeypatch):
    monkeypatch.setenv("FINZER_OBS_TRACING_ENABLED", "true")
    from app.observability.config import reset_observability_settings
    reset_observability_settings()
    try:
        with pytest.raises(ValueError, match="test failure"):
            with trace_span("failure") as span:
                raise ValueError("test failure")
        assert span.status == "error"
        assert span.error_type == "ValueError"
        assert current_span() is None
    finally:
        reset_observability_settings()


def test_metrics_count_latency_and_failures(monkeypatch):
    monkeypatch.setenv("FINZER_OBS_METRICS_ENABLED", "true")
    from app.observability.config import reset_observability_settings
    reset_observability_settings()
    try:
        meter = AgentMetrics()
        with meter.time_operation("rag"):
            pass
        with pytest.raises(RuntimeError):
            with meter.time_operation("rag"):
                raise RuntimeError("failure")
        snapshot = meter.snapshot()
        assert snapshot["operations"]["rag"] == {"error": 1, "success": 1}
        assert snapshot["latency_ms"]["rag"]["count"] == 2
        assert snapshot["latency_ms"]["rag"]["min"] >= 0
        with pytest.raises(ValueError):
            meter.record_operation("unbounded-custom-label")
        meter.reset()
        assert meter.snapshot()["operations"] == {}
    finally:
        reset_observability_settings()


def test_retry_requires_explicit_safety():
    attempts = []
    with pytest.raises(RetryNotAllowedError):
        retry_call(lambda: attempts.append(1))
    assert attempts == []


def test_retry_is_bounded_and_backoff_is_deterministic():
    attempts, sleeps = [], []
    def operation():
        attempts.append(1)
        if len(attempts) < 3:
            raise TimeoutError("temporary")
        return "ok"
    policy = RetryPolicy(max_attempts=3, initial_delay_seconds=0.1,
                         max_delay_seconds=1, jitter_ratio=0)
    assert retry_call(operation, retry_safe=True, policy=policy, sleep=sleeps.append) == "ok"
    assert len(attempts) == 3
    assert sleeps == pytest.approx([0.1, 0.2])


def test_retry_exhaustion_does_not_retry_forever():
    attempts = []
    def operation():
        attempts.append(1)
        raise ConnectionError("down")
    with pytest.raises(ConnectionError):
        retry_call(operation, retry_safe=True,
                   policy=RetryPolicy(max_attempts=2, initial_delay_seconds=0,
                                      max_delay_seconds=0, jitter_ratio=0),
                   sleep=lambda _: None)
    assert len(attempts) == 2


def test_circuit_breaker_opens_and_recovers():
    clock = [0.0]
    breaker = CircuitBreaker(CircuitBreakerPolicy(failure_threshold=2,
                              recovery_timeout_seconds=10), clock=lambda: clock[0])
    def unavailable():
        raise ConnectionError("unavailable")
    with pytest.raises(ConnectionError):
        breaker.call(unavailable)
    assert breaker.state is CircuitState.CLOSED
    with pytest.raises(ConnectionError):
        breaker.call(unavailable)
    assert breaker.state is CircuitState.OPEN
    called = []
    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: called.append(1))
    assert called == []
    clock[0] = 10.0
    assert breaker.call(lambda: "healthy") == "healthy"
    assert breaker.state is CircuitState.CLOSED


class _DocumentBackend:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error
    def retrieve(self, **kwargs):
        if self.error:
            raise self.error
        return self.result


def test_document_rag_empty_success():
    backend = _DocumentBackend({"context": "", "sources": [], "source_count": 0,
                                "total_tokens": 0})
    response = DocumentRAGTool(backend).execute(query="example", document_key="doc-1")
    assert response.status == "success"
    assert response.data.source_count == 0


def test_document_rag_backend_error_is_structured():
    response = DocumentRAGTool(_DocumentBackend(error=ConnectionError("down"))).execute(
        query="example", document_key="doc-1")
    assert response.status == "error"
    assert response.error.type == "RETRIEVAL_ERROR"
    assert response.error.retryable is True


class _NewsBackend:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error
    def retrieve(self, **kwargs):
        if self.error:
            raise self.error
        return self.result


def test_news_rag_empty_success():
    response = NewsRAGTool(_NewsBackend({"query": "example", "source_count": 0,
                                        "sources": []})).execute(query="example")
    assert response.status == "success"
    assert response.data.source_count == 0


def test_news_rag_backend_error_is_structured():
    response = NewsRAGTool(_NewsBackend(error=TimeoutError("down"))).execute(query="example")
    assert response.status == "error"
    assert response.error.type == "RETRIEVAL_ERROR"
    assert response.error.retryable is True
