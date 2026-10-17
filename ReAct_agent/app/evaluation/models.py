
"""Shared evaluation contracts for the Finzer ReAct agent (Phase 7)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvaluationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"


class RetrievalItem(BaseModel):
    """A retrieved chunk with its ranking and optional source metadata."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    rank: int = Field(ge=1)
    score: float | None = None
    source_id: str | None = None


class RAGEvaluationCase(BaseModel):
    """Ground truth and retrieved results for one RAG query."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    relevant_chunk_ids: set[str] = Field(default_factory=set)
    retrieved: list[RetrievalItem] = Field(default_factory=list)
    generated_answer: str | None = None
    reference_answer: str | None = None

    @model_validator(mode="after")
    def check_unique_ranks_and_chunks(self) -> "RAGEvaluationCase":
        ranks = [item.rank for item in self.retrieved]
        chunk_ids = [item.chunk_id for item in self.retrieved]

        if len(ranks) != len(set(ranks)):
            raise ValueError("retrieved ranks must be unique")

        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("retrieved chunk_ids must be unique")

        return self


class AgentEvaluationCase(BaseModel):
    """Expected and observed agent behavior for a deterministic test case."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    user_request: str = Field(min_length=1)

    expected_tool_names: list[str] = Field(default_factory=list)
    actual_tool_names: list[str] = Field(default_factory=list)

    expected_final_status: str | None = None
    actual_final_status: str | None = None

    expected_approval_required: bool | None = None
    actual_approval_required: bool | None = None

    task_completed: bool | None = None


class MetricResult(BaseModel):
    """One metric result, including explicit unavailability where appropriate."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    value: float | None = Field(default=None, ge=0.0, le=1.0)
    status: EvaluationStatus = EvaluationStatus.SKIPPED
    details: dict[str, Any] = Field(default_factory=dict)


class EvaluationReport(BaseModel):
    """Collection of results for one RAG or agent evaluation case."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    evaluator: str = Field(min_length=1)
    metrics: list[MetricResult] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
