"""Focused Phase 7 integration checks. Run from the ReAct_agent project root.

No external LLM, MCP service, or database is required for these tests.
"""

import pytest

from app.agent.graph import AgentDecision
from app.agent.state import AgentState, ExecutionStatus
from app.observability.config import reset_observability_settings
from app.observability.metrics import metrics
from app.tools.executor import FinzerToolExecutor, ToolExecutionError
from app.tools.news_rag import NewsRAGTool
from app.tools.document_rag import DocumentRAGTool
from test_governance import make_system, tool_decision


@pytest.fixture(autouse=True)
def isolated_metrics(monkeypatch):
    monkeypatch.setenv("FINZER_OBS_METRICS_ENABLED", "true")
    reset_observability_settings()
    metrics.reset()
    yield
    metrics.reset()
    reset_observability_settings()


def _count(category, outcome):
    return metrics.snapshot()["operations"].get(category, {}).get(outcome, 0)


def test_failed_graph_run_records_error_not_success():
    graph, *_ = make_system(tool_decision("unregistered_tool"))
    result = graph.run(AgentState(user_query="Test unknown tool"))
    assert result.execution_status == ExecutionStatus.FAILED
    assert _count("agent", "error") >= 1
    assert _count("agent", "success") == 0
    assert metrics.snapshot()["latency_ms"]["agent"]["count"] >= 1


def test_pending_graph_run_records_pending_not_success():
    graph, *_ = make_system(tool_decision("wishlist_add", asset="Example"))
    result = graph.run(AgentState(user_query="Add Example to wishlist", user_id="user-1"))
    assert result.execution_status == ExecutionStatus.WAITING_FOR_APPROVAL
    assert _count("agent", "pending") >= 1
    assert _count("agent", "success") == 0


class _Backend:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def retrieve(self, **kwargs):
        if self.error is not None:
            raise self.error
        return self.response


@pytest.mark.parametrize("tool_name,tool,arguments", [
    ("news_rag", NewsRAGTool(_Backend({"query": "example", "sources": [], "source_count": 0})), {"query": "example"}),
    ("document_rag", DocumentRAGTool(_Backend({"context": "", "sources": [], "source_count": 0, "total_tokens": 0})), {"query": "example", "document_key": "doc-1"}),
])
def test_executor_local_rag_records_one_retrieval(tool_name, tool, arguments):
    executor = FinzerToolExecutor(**({"news_tool": tool} if tool_name == "news_rag" else {"document_tool": tool}))
    result = executor.execute(tool_name=tool_name, arguments=arguments)
    assert result["status"] == "success"
    assert _count("rag", "success") == 1
    assert metrics.snapshot()["latency_ms"]["rag"]["count"] == 1
    assert _count("mcp", "success") == 0


def test_executor_local_rag_failure_records_once():
    executor = FinzerToolExecutor(news_tool=NewsRAGTool(_Backend(error=ConnectionError("backend unavailable"))))
    with pytest.raises(ToolExecutionError):
        executor.execute(tool_name="news_rag", arguments={"query": "example"})
    assert _count("rag", "error") == 1
    assert metrics.snapshot()["latency_ms"]["rag"]["count"] == 1
    assert _count("rag", "success") == 0
