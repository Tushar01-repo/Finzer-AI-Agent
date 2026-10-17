"""Offline tests for FinzerToolExecutor. Run: python -m pytest test_executor.py -v"""
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.tools.executor import FinzerToolExecutor, ToolExecutionError


def test_mcp_routes_to_registered_server():
    calls = []
    def call(server, name, args):
        calls.append((server, name, args))
        return {"status": "success", "data": {"price": 123}}
    result = FinzerToolExecutor(mcp_call=call).execute(
        tool_name="gold_spot_price", arguments={"currency": "INR"}
    )
    assert calls == [("finzer-gold-mcp", "gold_spot_price", {"currency": "INR"})]
    assert result["data"]["price"] == 123


def test_mutual_fund_routes_to_own_server():
    calls = []
    def call(server, name, args):
        calls.append((server, name, args))
        return {"status": "success"}
    FinzerToolExecutor(mcp_call=call).execute(
        tool_name="search_mutual_funds", arguments={"query": "SBI"}
    )
    assert calls == [("finzer-mutual-fund-mcp", "search_mutual_funds", {"query": "SBI"})]


def test_unknown_tool_is_rejected():
    with pytest.raises(KeyError, match="Unknown tool"):
        FinzerToolExecutor().execute(tool_name="not_a_tool", arguments={})


@pytest.mark.parametrize("tool", ["wishlist_add", "wishlist_remove"])
def test_write_tools_are_blocked(tool):
    with pytest.raises(PermissionError, match="Write tool blocked"):
        FinzerToolExecutor(user_context_available=True, mcp_call=lambda *a: None).execute(
            tool_name=tool, arguments={}
        )


def test_user_context_is_required_for_wishlist_read():
    with pytest.raises(PermissionError, match="Authenticated user context"):
        FinzerToolExecutor(mcp_call=lambda *a: None).execute(
            tool_name="wishlist_get", arguments={}
        )


def test_wishlist_read_allowed_with_context():
    result = FinzerToolExecutor(
        user_context_available=True,
        mcp_call=lambda *a: {"status": "success", "data": []},
    ).execute(tool_name="wishlist_get", arguments={})
    assert result["status"] == "success"


def test_missing_mcp_connection_is_reported():
    with pytest.raises(ToolExecutionError, match="MCP connection is not configured"):
        FinzerToolExecutor().execute(tool_name="gold_spot_price", arguments={})


def test_arguments_must_be_dictionary():
    with pytest.raises(TypeError, match="dictionary"):
        FinzerToolExecutor(mcp_call=lambda *a: None).execute(
            tool_name="gold_spot_price", arguments=["INR"]
        )


def test_document_rag_forwards_arguments():
    calls = []
    class DocumentTool:
        def execute(self, *, query, document_key, top_k=5, max_context_tokens=4000):
            calls.append((query, document_key, top_k, max_context_tokens))
            return {"status": "success", "data": {"sources": []}}
    result = FinzerToolExecutor(document_tool=DocumentTool()).execute(
        tool_name="document_rag",
        arguments={"query": "What is the issue size?", "document_key": "ipo-123", "top_k": 3},
    )
    assert calls == [("What is the issue size?", "ipo-123", 3, 4000)]
    assert result["status"] == "success"


def test_news_rag_forwards_filters():
    calls = []
    class NewsTool:
        def execute(self, *, query, top_k=5, company=None, published_after=None, published_before=None):
            calls.append((query, top_k, company, published_after, published_before))
            return {"status": "success", "data": {"sources": []}}
    FinzerToolExecutor(news_tool=NewsTool()).execute(
        tool_name="news_rag",
        arguments={"query": "earnings", "company": "Infosys", "published_after": "2026-01-01"},
    )
    assert calls == [("earnings", 5, "Infosys", "2026-01-01", None)]


def test_local_tool_rejects_missing_required_arguments():
    class DocumentTool:
        def execute(self, *, query, document_key):
            raise AssertionError("Must not execute")
    with pytest.raises(TypeError):
        FinzerToolExecutor(document_tool=DocumentTool()).execute(
            tool_name="document_rag", arguments={"query": "question"}
        )


def test_local_tool_rejects_unexpected_arguments():
    class NewsTool:
        def execute(self, *, query):
            raise AssertionError("Must not execute")
    with pytest.raises(TypeError):
        FinzerToolExecutor(news_tool=NewsTool()).execute(
            tool_name="news_rag", arguments={"query": "news", "unexpected": True}
        )


@pytest.mark.parametrize("tool", ["gold_spot_price", "document_rag"])
def test_explicit_error_response_raises(tool):
    response = {"status": "error", "error": {"message": "upstream failed"}}
    class FakeTool:
        def execute(self, **kwargs):
            return response
    executor = FinzerToolExecutor(
        mcp_call=lambda *a: response,
        document_tool=FakeTool(),
    )
    with pytest.raises(ToolExecutionError, match="upstream failed"):
        executor.execute(tool_name=tool, arguments={"query": "test", "document_key": "x"} if tool == "document_rag" else {})


def test_pydantic_response_is_serialized():
    class Response(BaseModel):
        status: str = "success"
        count: int = 2
    class NewsTool:
        def execute(self, *, query):
            return Response()
    result = FinzerToolExecutor(news_tool=NewsTool()).execute(
        tool_name="news_rag", arguments={"query": "news"}
    )
    assert result == {"status": "success", "count": 2}
