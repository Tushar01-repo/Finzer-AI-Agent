
"""
Finzer AI Agent - Governance Models
Phase 5: Governance and Human-in-the-Loop

Defines:
    - PolicyDecision
    - PolicyEvaluation
    - ApprovalRequest
    - ApprovalResolution

These are data contracts only.
Policy enforcement and approval management are implemented separately.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.state import ApprovalStatus, ToolCall


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class GovernanceModel(BaseModel):
    """Base model for strict governance data validation."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class PolicyDecision(str, Enum):
    """Possible outcomes of a tool authorization check."""

    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


class PolicyEvaluation(GovernanceModel):
    """Authorization result for a proposed tool call."""

    decision: PolicyDecision

    call_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    reason: str = Field(min_length=1)

    evaluated_at: datetime = Field(default_factory=utc_now)


class ApprovalRequest(GovernanceModel):
    """
    Represents a pending human approval request.

    The original ToolCall is retained to bind approval
    to the exact operation and arguments.
    """

    request_id: str = Field(
        default_factory=lambda: str(uuid4())
    )

    run_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)

    tool_call: ToolCall
    reason: str = Field(min_length=1)

    status: ApprovalStatus = ApprovalStatus.PENDING

    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime

    @model_validator(mode="after")
    def validate_request(self) -> "ApprovalRequest":

        if self.status != ApprovalStatus.PENDING:
            raise ValueError(
                "New approval requests must have pending status"
            )

        if self.created_at.tzinfo is None:
            raise ValueError(
                "created_at must be timezone-aware"
            )

        if self.expires_at.tzinfo is None:
            raise ValueError(
                "expires_at must be timezone-aware"
            )

        if self.expires_at <= self.created_at:
            raise ValueError(
                "expires_at must be later than created_at"
            )

        return self


class ApprovalResolution(GovernanceModel):
    """
    Records an explicit human approval or rejection.

    ApprovalManager will validate:
        - Request ownership
        - Matching tool call
        - Request expiration
        - Previous approval state
    """

    request_id: str = Field(min_length=1)
    call_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)

    decision: ApprovalStatus

    resolved_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_resolution(self) -> "ApprovalResolution":

        if self.decision not in (
            ApprovalStatus.APPROVED,
            ApprovalStatus.DENIED,
        ):
            raise ValueError(
                "Resolution must be approved or denied"
            )

        return self
