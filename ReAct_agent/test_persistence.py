"""Phase 6 integration tests. Run ONLY against a dedicated PostgreSQL test DB.

PowerShell:
  $env:FINZER_TEST_DATABASE_URL = 'postgresql://.../finzer_test'
  python -m pytest .\test_persistence.py -v

Tests use unique IDs and clean up their own rows. Never point at production.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

from app.agent.state import AgentState, ApprovalStatus, ToolCall
from app.governance.approval import (
    ApprovalAlreadyResolvedError, ApprovalManager, ApprovalPermissionError,
)
from app.governance.audit import AuditEventType, GovernanceAuditLogger
from app.persistence import database
from app.persistence.checkpointer import AgentCheckpointer
from app.persistence.repository import (
    AgentRunRepository, ApprovalRepository, AuditRepository,
    PersistenceConflictError, ToolExecutionRepository,
)


def uid(prefix):
    return f"phase6-{prefix}-{uuid4().hex}"


@pytest.fixture(scope="session", autouse=True)
def test_database():
    url = os.getenv("FINZER_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("Set FINZER_TEST_DATABASE_URL to a dedicated PostgreSQL test database")
    # database.get_connection reads DATABASE_URL dynamically.
    old = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        database.initialize_schema()
        yield
    finally:
        if old is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old


@pytest.fixture
def run_id():
    value = uid("run")
    yield value
    with database.get_connection() as conn:
        # Approval/audit/tool tables have no FK to runs; clean independently.
        conn.execute("DELETE FROM agent_tool_executions WHERE run_id = %s", (value,))
        conn.execute("DELETE FROM agent_audit_events WHERE run_id = %s", (value,))
        conn.execute("DELETE FROM agent_approval_requests WHERE run_id = %s", (value,))
        conn.execute("DELETE FROM agent_runs WHERE run_id = %s", (value,))


def test_schema_constraints_present():
    with database.get_connection() as conn:
        constraints = conn.execute("""
            SELECT indexdef FROM pg_indexes
            WHERE schemaname = current_schema()
              AND tablename = 'agent_tool_executions'
        """).fetchall()
    definitions = " ".join(r["indexdef"] for r in constraints)
    assert "(run_id, call_id)" in definitions
    assert "(approval_request_id)" in definitions


def test_agent_run_optimistic_concurrency(run_id):
    repo = AgentRunRepository()
    state = AgentState(run_id=run_id, user_id="test-user", user_query="Gold price")
    version = repo.create(state)
    recovered, recovered_version = AgentRunRepository().get(run_id)
    assert recovered.user_query == "Gold price"
    assert recovered_version == version
    recovered.step_count = 1
    new_version = repo.update(recovered, expected_version=version)
    assert new_version == version + 1
    with pytest.raises(PersistenceConflictError):
        repo.update(recovered, expected_version=version)


def test_checkpoint_restart_and_history(run_id):
    cp = AgentCheckpointer()
    state = AgentState(run_id=run_id, user_id="test-user", user_query="Summarize news")
    first_id, version = cp.save(state)
    state.step_count = 2
    second_id, version2 = AgentCheckpointer().save(state, expected_version=version)
    assert version2 == version + 1
    assert second_id > first_id
    assert AgentCheckpointer().latest(run_id).state.step_count == 2
    assert AgentCheckpointer().get(first_id).state.step_count == 0
    assert len(AgentCheckpointer().history(run_id)) == 2
    with pytest.raises(PersistenceConflictError):
        cp.save(state, expected_version=version)


def test_approval_persists_and_cannot_be_reused(run_id):
    repo = ApprovalRepository()
    manager1 = ApprovalManager(repository=repo)
    call = ToolCall(call_id=uid("call"), tool_name="wishlist_add", arguments={"asset": "Gold"})
    request = manager1.create_request(
        run_id=run_id, user_id="owner", tool_call=call, reason="Write needs approval"
    )
    manager2 = ApprovalManager(repository=ApprovalRepository())
    assert manager2.get_request(request.request_id).tool_call == call
    with pytest.raises(ApprovalPermissionError):
        manager2.resolve(request_id=request.request_id, user_id="intruder", approve=True)
    assert manager2.get_resolution(request.request_id) is None
    resolution = manager2.resolve(request_id=request.request_id, user_id="owner", approve=True)
    assert resolution.decision == ApprovalStatus.APPROVED
    assert ApprovalManager(repository=ApprovalRepository()).validate_resume(
        request_id=request.request_id, run_id=run_id, user_id="owner", tool_call=call
    )
    assert manager1.get_resolution(request.request_id).decision == ApprovalStatus.APPROVED
    with pytest.raises(ApprovalAlreadyResolvedError):
        manager1.resolve(request_id=request.request_id, user_id="owner", approve=True)
    assert not manager1.validate_resume(
        request_id=request.request_id, run_id=run_id, user_id="owner",
        tool_call=ToolCall(call_id=call.call_id, tool_name=call.tool_name,
                           arguments={"asset": "Silver"}),
    )


def test_durable_audit_retrieval(run_id):
    logger = GovernanceAuditLogger(repository=AuditRepository())
    saved = logger.record(
        event_type=AuditEventType.TOOL_BLOCKED, run_id=run_id,
        tool_name="wishlist_add", call_id=uid("call"), outcome="denied",
        reason="Test policy", user_id="test-user",
    )
    recovered = GovernanceAuditLogger(repository=AuditRepository()).get_events(run_id=run_id)
    assert len(recovered) == 1
    assert recovered[0].event_id == saved.event_id
    assert recovered[0].event_type == AuditEventType.TOOL_BLOCKED
    assert GovernanceAuditLogger(repository=AuditRepository()).get_events(
        run_id=run_id, event_type=AuditEventType.TOOL_EXECUTED
    ) == []
    with pytest.raises(RuntimeError):
        logger.clear()


def test_tool_reservation_survives_new_repository(run_id):
    call_id, approval_id = uid("call"), uid("approval")
    first = ToolExecutionRepository()
    assert first.reserve(run_id=run_id, call_id=call_id, tool_name="wishlist_add",
                         approval_request_id=approval_id)
    second = ToolExecutionRepository()
    assert not second.reserve(run_id=run_id, call_id=call_id, tool_name="wishlist_add",
                              approval_request_id=approval_id)
    assert not second.reserve(run_id=run_id, call_id=uid("other"),
                              tool_name="wishlist_add", approval_request_id=approval_id)
    assert second.get(run_id=run_id, call_id=call_id)["status"] == "reserved"
    first.finish(run_id=run_id, call_id=call_id, status="succeeded", result={"ok": True})
    assert second.get(run_id=run_id, call_id=call_id)["result"] == {"ok": True}
    with pytest.raises(PersistenceConflictError):
        first.finish(run_id=run_id, call_id=call_id, status="succeeded", result={})


def test_ambiguous_reserved_tool_call_is_not_replayed(run_id):
    """A crash can leave 'reserved': it must not be automatically dispatched again."""
    repo = ToolExecutionRepository()
    call_id, approval_id = uid("call"), uid("approval")
    assert repo.reserve(run_id=run_id, call_id=call_id, tool_name="wishlist_add",
                        approval_request_id=approval_id)
    assert ToolExecutionRepository().get(run_id=run_id, call_id=call_id)["status"] == "reserved"
    assert not ToolExecutionRepository().reserve(
        run_id=run_id, call_id=call_id, tool_name="wishlist_add",
        approval_request_id=approval_id,
    )


def test_graph_restart_approval_resume_e2e(run_id):
    """PostgreSQL-backed graph restart -> approval -> one MCP write -> recovery.

    Uses a deterministic model and an instrumented MCP transport so that no
    external service or paid LLM is required.
    """
    from app.agent.graph import AgentDecision, ReActGraph
    from app.agent.state import ExecutionStatus, ObservationStatus
    from app.tools.executor import FinzerToolExecutor

    user_id = "phase6-e2e-user"
    mcp_calls = []

    def fake_mcp(server, tool, args):
        mcp_calls.append((server, tool, dict(args)))
        return {"status": "success", "data": {"ok": True}}

    class DecisionScript:
        def __init__(self, decisions):
            self.decisions = list(decisions)

        def decide(self, *, context, available_tools):
            assert self.decisions, "Unexpected model invocation"
            decision = self.decisions.pop(0)
            if decision.action == "tool":
                assert decision.tool_name in {t.name for t in available_tools}
            return decision

    def new_graph(decisions):
        # Every component is reconstructed to simulate a process restart.
        approvals = ApprovalManager(repository=ApprovalRepository())
        audit = GovernanceAuditLogger(repository=AuditRepository())
        executor = FinzerToolExecutor(
            mcp_call=fake_mcp,
            approval_manager=approvals,
            execution_repository=ToolExecutionRepository(),
            user_context_available=True,
        )
        graph = ReActGraph(
            decision_model=DecisionScript(decisions),
            tool_executor=executor,
            approval_manager=approvals,
            audit_logger=audit,
            user_context_available=True,
            checkpointer=AgentCheckpointer(),
        )
        return graph, approvals, audit, executor

    before_restart, approvals1, _, _ = new_graph([
        AgentDecision(
            action="tool",
            tool_name="wishlist_add",
            arguments={"asset": "Example"},
        ),
    ])
    paused = before_restart.run(AgentState(
        run_id=run_id,
        user_id=user_id,
        user_query="Add Example to my wishlist",
    ))
    assert paused.execution_status == ExecutionStatus.WAITING_FOR_APPROVAL
    assert paused.pending_tool_call is not None
    assert paused.approval.status == ApprovalStatus.PENDING
    assert mcp_calls == []

    request_id = paused.approval.reason.rsplit("[request_id=", 1)[1].rstrip("]")
    request = approvals1.get_request(request_id)
    assert request.tool_call == paused.pending_tool_call

    # Simulated restart: discard the graph, repositories, manager and model.
    after_restart, approvals2, audit2, executor2 = new_graph([
        AgentDecision(action="finish", message="Wishlist updated."),
    ])
    restored = after_restart.load_checkpoint(run_id)
    assert restored.model_dump(mode="json") == paused.model_dump(mode="json")
    assert approvals2.get_request(request_id).request_id == request_id

    finished = after_restart.resolve_approval(
        state=restored,
        request_id=request_id,
        user_id=user_id,
        approve=True,
    )
    assert finished.execution_status == ExecutionStatus.COMPLETED
    assert finished.tool_call_count == 1
    assert finished.final_answer == "Wishlist updated."
    assert len(mcp_calls) == 1
    assert mcp_calls[0][1] == "wishlist_add"
    assert any(
        obs.status == ObservationStatus.SUCCESS
        and obs.call_id == request.tool_call.call_id
        for obs in finished.observations
    )

    # A third process sees the final checkpoint and the durable audit trail.
    after_second_restart, _, audit3, executor3 = new_graph([])
    final_state = after_second_restart.load_checkpoint(run_id)
    assert final_state.execution_status == ExecutionStatus.COMPLETED
    assert final_state.tool_call_count == 1
    assert len(AgentCheckpointer().history(run_id)) >= 3
    assert audit3.get_events(
        run_id=run_id, event_type=AuditEventType.AGENT_RESUMED
    )
    assert audit3.get_events(
        run_id=run_id, event_type=AuditEventType.TOOL_EXECUTED
    )

    execution = ToolExecutionRepository().get(
        run_id=run_id, call_id=request.tool_call.call_id
    )
    assert execution["status"] == "succeeded"

    # Even after a restart, an attempt to replay the same write is rejected.
    with pytest.raises(PermissionError):
        executor3.execute(
            tool_name="wishlist_add",
            arguments=request.tool_call.arguments,
            run_id=run_id,
            user_id=user_id,
            call_id=request.tool_call.call_id,
            approval_request_id=request_id,
        )
    assert len(mcp_calls) == 1
