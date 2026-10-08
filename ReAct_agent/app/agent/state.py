"""Typed execution state for the Finzer ReAct agent (Phase 3.1).

Pure data contracts: no tool calls, database access, or LLM invocations.
Compatible with Pydantic v2 and Python 3.10+.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class NextAction(str, Enum):
    DECIDE = "decide"
    TOOL = "tool"
    CLARIFY = "clarify"
    ANSWER = "answer"
    WAIT_APPROVAL = "wait_approval"
    FINISH = "finish"


class ExecutionStatus(str, Enum):
    RUNNING = "running"
    WAITING_FOR_USER = "waiting_for_user"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class ObservationStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    DENIED = "denied"


class ApprovalStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class EvidenceStatus(str, Enum):
    NOT_CHECKED = "not_checked"
    PASSED = "passed"
    FAILED = "failed"


class EntityType(str, Enum):
    MUTUAL_FUND = "MUTUAL_FUND"
    GOLD = "GOLD"
    COMPANY = "COMPANY"
    IPO_DOCUMENT = "IPO_DOCUMENT"
    NEWS_TOPIC = "NEWS_TOPIC"


class ConversationMessage(StrictModel):
    role: MessageRole
    content: str
    tool_call_id: str | None = None


class ResolvedEntity(StrictModel):
    entity_type: EntityType
    name: str = Field(min_length=1)
    canonical_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCall(StrictModel):
    call_id: str = Field(default_factory=lambda: str(uuid4()))
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolError(StrictModel):
    type: str = Field(min_length=1)
    message: str
    retryable: bool = False


class ToolObservation(StrictModel):
    call_id: str
    tool_name: str
    status: ObservationStatus
    data: Any | None = None
    error: ToolError | None = None
    observed_at: datetime = Field(default_factory=datetime.utcnow)

    @model_validator(mode="after")
    def check_result(self) -> "ToolObservation":
        if self.status == ObservationStatus.SUCCESS and self.error is not None:
            raise ValueError("Successful observations cannot contain an error")
        if self.status != ObservationStatus.SUCCESS and self.error is None:
            raise ValueError("Failed or denied observations must contain an error")
        return self


class Evidence(StrictModel):
    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    call_id: str
    tool_name: str
    source_name: str | None = None
    source_url: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentError(StrictModel):
    type: str
    message: str
    step: int = Field(default=0, ge=0)
    retryable: bool = False


class Approval(StrictModel):
    status: ApprovalStatus = ApprovalStatus.NOT_REQUIRED
    call_id: str | None = None
    reason: str | None = None


class EvidenceValidation(StrictModel):
    status: EvidenceStatus = EvidenceStatus.NOT_CHECKED
    issues: list[str] = Field(default_factory=list)


class AgentState(StrictModel):
    """Serializable snapshot of one agent run.

    Counters are recorded here; the future execution gate enforces budgets.
    """

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str | None = None
    user_id: str | None = None
    user_query: str = Field(min_length=1)

    messages: list[ConversationMessage] = Field(default_factory=list)
    conversation_summary: str = ""
    active_entities: list[ResolvedEntity] = Field(default_factory=list)

    intent: str | None = None
    next_action: NextAction = NextAction.DECIDE
    execution_status: ExecutionStatus = ExecutionStatus.RUNNING
    pending_tool_call: ToolCall | None = None

    observations: list[ToolObservation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    errors: list[AgentError] = Field(default_factory=list)

    approval: Approval = Field(default_factory=Approval)
    step_count: int = Field(default=0, ge=0)
    tool_call_count: int = Field(default=0, ge=0)

    evidence_validation: EvidenceValidation = Field(default_factory=EvidenceValidation)
    final_answer: str | None = None

    @model_validator(mode="after")
    def check_consistency(self) -> "AgentState":
        if self.next_action in (NextAction.TOOL, NextAction.WAIT_APPROVAL):
            if self.pending_tool_call is None:
                raise ValueError("A tool/approval action requires pending_tool_call")
        if self.approval.status == ApprovalStatus.PENDING:
            if self.pending_tool_call is None:
                raise ValueError("Pending approval requires pending_tool_call")
            if self.approval.call_id != self.pending_tool_call.call_id:
                raise ValueError("Approval call_id must match pending tool call")
        if self.execution_status == ExecutionStatus.COMPLETED and not self.final_answer:
            raise ValueError("Completed execution requires final_answer")
        return self
