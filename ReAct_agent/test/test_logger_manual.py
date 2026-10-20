from app.observability.logger import get_logger, log_context

logger = get_logger("finzer.agent")

with log_context(
    run_id="run-123",
    user_id="user-456",
    trace_id="trace-789",
):
    logger.info(
        "agent_started",
        tool_name="wishlist_add",
        api_key="sk-example-secret",
    )

    logger.warning(
        "tool_latency_high",
        latency_ms=1250,
    )