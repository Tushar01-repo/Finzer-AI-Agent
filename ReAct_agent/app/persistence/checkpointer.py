"""Durable AgentState checkpoints for Finzer ReAct Agent (Phase 6).

Requires tables created by app.persistence.database.initialize_schema().
Checkpoints and the current run snapshot are updated in one transaction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from psycopg.types.json import Jsonb

from app.agent.state import AgentState
from app.persistence.database import get_connection
from app.persistence.repository import PersistenceConflictError


@dataclass(frozen=True)
class SavedCheckpoint:
    checkpoint_id: int
    run_id: str
    step_count: int
    state: AgentState
    created_at: datetime


class AgentCheckpointer:
    """Append-only checkpoints with optimistic concurrency on agent_runs.

    Call save(state) to create a run and its first checkpoint atomically.
    For subsequent saves, pass the version returned by the previous save.
    """

    def save(self, state: AgentState, *, expected_version: int | None = None) -> tuple[int, int]:
        """Return (checkpoint_id, new_run_version).

        If expected_version is None, the run must not already exist.
        Otherwise the run must exist with exactly that version.
        """
        payload = Jsonb(state.model_dump(mode="json"))
        with get_connection() as conn:
            if expected_version is None:
                row = conn.execute(
                    """INSERT INTO agent_runs
                           (run_id, user_id, state, execution_status)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (run_id) DO NOTHING
                       RETURNING version""",
                    (state.run_id, state.user_id, payload,
                     state.execution_status.value),
                ).fetchone()
            else:
                row = conn.execute(
                    """UPDATE agent_runs
                          SET user_id = %s, state = %s, execution_status = %s,
                              version = version + 1, updated_at = NOW()
                        WHERE run_id = %s AND version = %s
                        RETURNING version""",
                    (state.user_id, payload, state.execution_status.value,
                     state.run_id, expected_version),
                ).fetchone()

            if row is None:
                raise PersistenceConflictError(
                    f"Run {state.run_id} already exists, is missing, or version changed"
                )

            checkpoint = conn.execute(
                """INSERT INTO agent_checkpoints (run_id, state, step_count)
                   VALUES (%s, %s, %s)
                   RETURNING checkpoint_id""",
                (state.run_id, payload, state.step_count),
            ).fetchone()
            return int(checkpoint["checkpoint_id"]), int(row["version"])

    def latest(self, run_id: str) -> SavedCheckpoint | None:
        """Load the most recent durable snapshot for a run."""
        with get_connection() as conn:
            row = conn.execute(
                """SELECT checkpoint_id, run_id, step_count, state, created_at
                     FROM agent_checkpoints
                    WHERE run_id = %s
                    ORDER BY checkpoint_id DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
        return self._decode(row) if row else None

    def get(self, checkpoint_id: int) -> SavedCheckpoint | None:
        """Load a specific checkpoint by its ID."""
        with get_connection() as conn:
            row = conn.execute(
                """SELECT checkpoint_id, run_id, step_count, state, created_at
                     FROM agent_checkpoints WHERE checkpoint_id = %s""",
                (checkpoint_id,),
            ).fetchone()
        return self._decode(row) if row else None

    def history(self, run_id: str, *, limit: int = 20) -> list[SavedCheckpoint]:
        """Return newest-first checkpoints for inspection and debugging."""
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT checkpoint_id, run_id, step_count, state, created_at
                     FROM agent_checkpoints
                    WHERE run_id = %s
                    ORDER BY checkpoint_id DESC LIMIT %s""",
                (run_id, limit),
            ).fetchall()
        return [self._decode(row) for row in rows]

    @staticmethod
    def _decode(row: dict) -> SavedCheckpoint:
        return SavedCheckpoint(
            checkpoint_id=int(row["checkpoint_id"]),
            run_id=row["run_id"],
            step_count=int(row["step_count"]),
            state=AgentState.model_validate(row["state"]),
            created_at=row["created_at"],
        )
