
"""Deterministic agent behavior evaluation for Finzer ReAct."""

from __future__ import annotations

from collections import Counter

from app.evaluation.models import (
    AgentEvaluationCase,
    EvaluationReport,
    EvaluationStatus,
    MetricResult,
)


class AgentEvaluator:
    """Evaluate agent tool selection, execution, and approval behavior."""

    @staticmethod
    def _metric(
        name: str,
        value: float | None,
        *,
        details: dict | None = None,
    ) -> MetricResult:
        return MetricResult(
            name=name,
            value=value,
            status=(
                EvaluationStatus.SKIPPED
                if value is None
                else EvaluationStatus.PASS
            ),
            details=details or {},
        )

    def evaluate(self, case: AgentEvaluationCase) -> EvaluationReport:
        metrics: list[MetricResult] = []
        notes: list[str] = []

        expected = Counter(case.expected_tool_names)
        actual = Counter(case.actual_tool_names)

        matched = sum(
            min(count, actual[tool])
            for tool, count in expected.items()
        )

        expected_count = sum(expected.values())
        actual_count = sum(actual.values())

        tool_precision = (
            matched / actual_count
            if actual_count
            else (1.0 if expected_count == 0 else 0.0)
        )

        tool_recall = (
            matched / expected_count
            if expected_count
            else (1.0 if actual_count == 0 else 0.0)
        )

        tool_f1 = (
            2 * tool_precision * tool_recall
            / (tool_precision + tool_recall)
            if tool_precision + tool_recall > 0
            else 0.0
        )

        exact_tool_match = float(
            case.expected_tool_names == case.actual_tool_names
        )

        metrics.extend(
            [
                self._metric("tool_precision", tool_precision),
                self._metric("tool_recall", tool_recall),
                self._metric("tool_f1", tool_f1),
                self._metric("exact_tool_sequence", exact_tool_match),
            ]
        )

        if (
            case.expected_final_status is not None
            and case.actual_final_status is not None
        ):
            status_match = float(
                case.expected_final_status
                == case.actual_final_status
            )
        else:
            status_match = None

        metrics.append(
            self._metric("final_status_match", status_match)
        )

        if case.task_completed is None:
            task_completion = None
        else:
            task_completion = float(case.task_completed)

        metrics.append(
            self._metric("task_completion", task_completion)
        )

        if (
            case.expected_approval_required is not None
            and case.actual_approval_required is not None
        ):
            approval_match = float(
                case.expected_approval_required
                == case.actual_approval_required
            )
        else:
            approval_match = None

        metrics.append(
            self._metric("approval_requirement_match", approval_match)
        )

        if status_match is None:
            notes.append(
                "Final status comparison skipped because expected "
                "or actual status was not supplied."
            )

        if approval_match is None:
            notes.append(
                "Approval requirement comparison skipped because "
                "expected or actual approval information was missing."
            )

        return EvaluationReport(
            case_id=case.case_id,
            evaluator="agent",
            metrics=metrics,
            notes=notes,
        )
