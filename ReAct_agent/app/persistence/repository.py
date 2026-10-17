"""PostgreSQL persistence repositories for Finzer ReAct Agent (Phase 6).

Call initialize_schema() from app.persistence.database before using repositories.
"""
from __future__ import annotations

from typing import Any, Mapping
from psycopg.types.json import Jsonb

from app.agent.state import AgentState
from app.governance.models import ApprovalRequest
from app.persistence.database import get_connection


class PersistenceConflictError(RuntimeError):
    """Duplicate or concurrently modified record."""


def _json(value: Any) -> Jsonb:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return Jsonb(value)


class AgentRunRepository:
    def create(self, state: AgentState) -> int:
        with get_connection() as conn:
            row = conn.execute(
                """INSERT INTO agent_runs (run_id, user_id, state, execution_status)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (run_id) DO NOTHING RETURNING version""",
                (state.run_id, state.user_id, _json(state),
                 state.execution_status.value),
            ).fetchone()
        if row is None:
            raise PersistenceConflictError(f"Run already exists: {state.run_id}")
        return int(row["version"])

    def get(self, run_id: str) -> tuple[AgentState, int] | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT state, version FROM agent_runs WHERE run_id = %s",
                (run_id,),
            ).fetchone()
        return (
            (AgentState.model_validate(row["state"]), int(row["version"]))
            if row else None
        )

    def update(self, state: AgentState, *, expected_version: int) -> int:
        """Optimistic version check prevents lost concurrent updates."""
        with get_connection() as conn:
            row = conn.execute(
                """UPDATE agent_runs
                      SET state = %s, user_id = %s, execution_status = %s,
                          version = version + 1, updated_at = NOW()
                    WHERE run_id = %s AND version = %s
                    RETURNING version""",
                (_json(state), state.user_id, state.execution_status.value,
                 state.run_id, expected_version),
            ).fetchone()
        if row is None:
            raise PersistenceConflictError(
                f"Run missing or version changed: {state.run_id}"
            )
        return int(row["version"])


class ApprovalRepository:
    def create(self, request: ApprovalRequest) -> None:
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO agent_approval_requests
                       (request_id, run_id, user_id, payload, status, expires_at)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (request.request_id, request.run_id, request.user_id,
                 _json(request), request.status.value, request.expires_at),
            )

    def get(self, request_id: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM agent_approval_requests WHERE request_id = %s",
                (request_id,),
            ).fetchone()
        return dict(row) if row else None

    def resolve(self, request_id: str, *, user_id: str, decision: str) -> bool:
        """Atomic, owner-checked, single-use, unexpired resolution."""
        if decision not in ("approved", "denied"):
            raise ValueError("decision must be approved or denied")
        with get_connection() as conn:
            row = conn.execute(
                """UPDATE agent_approval_requests
                      SET status = %s, updated_at = NOW()
                    WHERE request_id = %s AND user_id = %s
                      AND status = 'pending'
                      AND (expires_at IS NULL OR expires_at > NOW())
                    RETURNING request_id""",
                (decision, request_id, user_id),
            ).fetchone()
        return row is not None


class AuditRepository:
    def append(
        self, event_type: str, payload: Mapping[str, Any],
        *, run_id: str | None = None, user_id: str | None = None
    ) -> int:
        with get_connection() as conn:
            row = conn.execute(
                """INSERT INTO agent_audit_events
                       (run_id, user_id, event_type, payload)
                   VALUES (%s, %s, %s, %s) RETURNING event_id""",
                (run_id, user_id, event_type, _json(dict(payload))),
            ).fetchone()
        return int(row["event_id"])

    def list_for_run(self, run_id: str) -> list[dict[str, Any]]:
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM agent_audit_events
                    WHERE run_id = %s ORDER BY event_id""",
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]


class ToolExecutionRepository:
    """Reserve each call and approval ID only once across restarts.

    A 'reserved' call may already have caused an external side effect.
    Do NOT automatically replay it after a crash without reconciliation.
    """

    def reserve(
        self, *, run_id: str, call_id: str, tool_name: str,
        approval_request_id: str | None = None
    ) -> bool:
        with get_connection() as conn:
            row = conn.execute(
                """INSERT INTO agent_tool_executions
                       (run_id, call_id, tool_name, approval_request_id, status)
                   VALUES (%s, %s, %s, %s, 'reserved')
                   ON CONFLICT DO NOTHING RETURNING call_id""",
                (run_id, call_id, tool_name, approval_request_id),
            ).fetchone()
        return row is not None

    def finish(
        self, *, run_id: str, call_id: str, status: str, result: Any
    ) -> None:
        if status not in ("succeeded", "failed", "unknown"):
            raise ValueError("Unsupported execution status")
        with get_connection() as conn:
            row = conn.execute(
                """UPDATE agent_tool_executions
                      SET status = %s, result = %s, updated_at = NOW()
                    WHERE run_id = %s AND call_id = %s AND status = 'reserved'
                    RETURNING call_id""",
                (status, _json(result), run_id, call_id),
            ).fetchone()
        if row is None:
            raise PersistenceConflictError(
                f"Tool call not reserved or already finalized: {run_id}/{call_id}"
            )

    def get(self, *, run_id: str, call_id: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            row = conn.execute(
                """SELECT * FROM agent_tool_executions
                    WHERE run_id = %s AND call_id = %s""",
                (run_id, call_id),
            ).fetchone()
        return dict(row) if row else None
