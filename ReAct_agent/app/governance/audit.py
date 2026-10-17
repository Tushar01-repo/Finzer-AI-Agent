
"""
Finzer AI Agent - Governance Audit Logger
Phase 5: Governance and Human-in-the-Loop

Responsibilities:
    - Record policy evaluations
    - Record approval requests and resolutions
    - Record tool execution outcomes
    - Record blocked operations
    - Record agent resume events

This implementation uses an in-memory, thread-safe audit store.
It does not execute tools or make authorization decisions.
"""

from __future__ import annotations

from enum import Enum
from threading import RLock
from typing import Any, TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.persistence.repository import AuditRepository

from app.governance.models import (
    ApprovalRequest,
    ApprovalResolution,
    PolicyEvaluation,
    utc_now,
)


class AuditEventType(str, Enum):
    POLICY_EVALUATED = "policy_evaluated"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    TOOL_EXECUTED = "tool_executed"
    TOOL_BLOCKED = "tool_blocked"
    AGENT_RESUMED = "agent_resumed"


class AuditEvent(BaseModel):
    """A single immutable governance audit record."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    event_id: str = Field(
        default_factory=lambda: str(uuid4())
    )

    event_type: AuditEventType

    run_id: str = Field(min_length=1)
    tool_name: str | None = None
    call_id: str | None = None
    request_id: str | None = None
    user_id: str | None = None

    outcome: str = Field(min_length=1)
    reason: str | None = None

    timestamp: Any = Field(default_factory=utc_now)


class GovernanceAuditLogger:
    """
    Audit logger with optional durable PostgreSQL repository.

    Only explicitly selected metadata is stored.
    Tool arguments and raw tool responses are excluded.
    """

    def __init__(self, *, repository: AuditRepository | None = None) -> None:
        self.repository = repository
        self._events: list[AuditEvent] = []
        self._lock = RLock()

    def record(
        self,
        *,
        event_type: AuditEventType,
        run_id: str,
        outcome: str,
        tool_name: str | None = None,
        call_id: str | None = None,
        request_id: str | None = None,
        user_id: str | None = None,
        reason: str | None = None,
    ) -> AuditEvent:
        """Record one governance audit event."""

        event = AuditEvent(
            event_type=event_type,
            run_id=run_id,
            tool_name=tool_name,
            call_id=call_id,
            request_id=request_id,
            user_id=user_id,
            outcome=outcome,
            reason=reason,
        )

        if self.repository is not None:
            # Write first: if persistence fails, never report an audit success.
            self.repository.append(
                event_type=event.event_type.value,
                payload=event.model_dump(mode="json"),
                run_id=event.run_id,
                user_id=event.user_id,
            )
        else:
            with self._lock:
                self._events.append(event)

        return event

    def record_policy(
        self,
        *,
        run_id: str,
        evaluation: PolicyEvaluation,
    ) -> AuditEvent:
        """Record a tool policy evaluation."""

        return self.record(
            event_type=AuditEventType.POLICY_EVALUATED,
            run_id=run_id,
            tool_name=evaluation.tool_name,
            call_id=evaluation.call_id,
            outcome=evaluation.decision.value,
            reason=evaluation.reason,
        )

    def record_approval_request(
        self,
        *,
        request: ApprovalRequest,
    ) -> AuditEvent:
        """Record the creation of a human approval request."""

        return self.record(
            event_type=AuditEventType.APPROVAL_REQUESTED,
            run_id=request.run_id,
            tool_name=request.tool_call.tool_name,
            call_id=request.tool_call.call_id,
            request_id=request.request_id,
            user_id=request.user_id,
            outcome="pending",
        )

    def record_approval_resolution(
        self,
        *,
        run_id: str,
        resolution: ApprovalResolution,
    ) -> AuditEvent:
        """Record a human approval or rejection."""

        return self.record(
            event_type=AuditEventType.APPROVAL_RESOLVED,
            run_id=run_id,
            call_id=resolution.call_id,
            request_id=resolution.request_id,
            user_id=resolution.user_id,
            outcome=resolution.decision.value,
        )

    def record_tool_executed(
        self,
        *,
        run_id: str,
        tool_name: str,
        call_id: str,
        success: bool,
    ) -> AuditEvent:
        """Record a completed tool execution."""

        return self.record(
            event_type=AuditEventType.TOOL_EXECUTED,
            run_id=run_id,
            tool_name=tool_name,
            call_id=call_id,
            outcome="success" if success else "failure",
        )

    def record_tool_blocked(
        self,
        *,
        run_id: str,
        tool_name: str,
        call_id: str,
        reason: str,
    ) -> AuditEvent:
        """Record an operation blocked by governance."""

        return self.record(
            event_type=AuditEventType.TOOL_BLOCKED,
            run_id=run_id,
            tool_name=tool_name,
            call_id=call_id,
            outcome="denied",
            reason=reason,
        )

    def record_agent_resumed(
        self,
        *,
        run_id: str,
        request_id: str,
    ) -> AuditEvent:
        """Record an agent resuming after approval."""

        return self.record(
            event_type=AuditEventType.AGENT_RESUMED,
            run_id=run_id,
            request_id=request_id,
            outcome="resumed",
        )

    def get_events(
        self,
        *,
        run_id: str | None = None,
        event_type: AuditEventType | None = None,
    ) -> list[AuditEvent]:
        """Retrieve audit events with optional filters."""

        if self.repository is not None:
            if run_id is None:
                raise ValueError(
                    "Persistent audit queries require run_id; "
                    "the current AuditRepository only supports list_for_run()."
                )
            rows = self.repository.list_for_run(run_id)
            events = [
                AuditEvent.model_validate(row["payload"])
                for row in rows
            ]
        else:
            with self._lock:
                events = list(self._events)

        if run_id is not None:
            events = [
                event for event in events
                if event.run_id == run_id
            ]

        if event_type is not None:
            events = [
                event for event in events
                if event.event_type == event_type
            ]

        return events

    def clear(self) -> None:
        """Clear in-memory audit records (testing only)."""

        if self.repository is not None:
            raise RuntimeError(
                "Cannot clear durable audit records; clear() is for in-memory tests only"
            )
        with self._lock:
            self._events.clear()
