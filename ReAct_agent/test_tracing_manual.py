import time

from app.observability.tracing import (
    add_span_attributes,
    trace_span,
)

with trace_span(
    "react_agent",
    run_id="run-123",
    user_id="user-456",
):
    with trace_span(
        "rag_retrieval",
        attributes={"top_k": 5},
    ):
        time.sleep(0.05)
        add_span_attributes(retrieved_chunks=5)

    with trace_span(
        "mcp_tool_execution",
        attributes={"tool_name": "wishlist_add"},
    ):
        time.sleep(0.02)