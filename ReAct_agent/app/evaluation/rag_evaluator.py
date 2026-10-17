
"""Deterministic RAG retrieval evaluation for Finzer."""

from __future__ import annotations

from app.evaluation.models import (
    EvaluationReport,
    EvaluationStatus,
    MetricResult,
    RAGEvaluationCase,
)


class RAGEvaluator:
    """Evaluate ranked retrieval against known relevant chunk IDs."""

    def __init__(self, k_values: tuple[int, ...] = (1, 3, 5, 10)):
        if not k_values or any(k <= 0 for k in k_values):
            raise ValueError("k_values must contain positive integers")

        self.k_values = tuple(sorted(set(k_values)))

    @staticmethod
    def _result(
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

    def evaluate(self, case: RAGEvaluationCase) -> EvaluationReport:
        relevant = case.relevant_chunk_ids
        ranked = sorted(case.retrieved, key=lambda item: item.rank)

        metrics: list[MetricResult] = []
        notes: list[str] = []

        for k in self.k_values:
            top_k = ranked[:k]
            relevant_hits = sum(
                item.chunk_id in relevant for item in top_k
            )

            precision = relevant_hits / k

            recall = (
                relevant_hits / len(relevant)
                if relevant
                else None
            )

            hit_rate = (
                float(relevant_hits > 0)
                if relevant
                else None
            )

            first_relevant_rank = next(
                (
                    index
                    for index, item in enumerate(top_k, start=1)
                    if item.chunk_id in relevant
                ),
                None,
            )

            mrr = (
                1.0 / first_relevant_rank
                if first_relevant_rank is not None
                else 0.0
            ) if relevant else None

            details = {
                "k": k,
                "relevant_hits": relevant_hits,
                "total_relevant": len(relevant),
                "retrieved_count": len(top_k),
            }

            metrics.extend(
                [
                    self._result(
                        f"precision@{k}", precision, details=details
                    ),
                    self._result(
                        f"recall@{k}", recall, details=details
                    ),
                    self._result(
                        f"hit_rate@{k}", hit_rate, details=details
                    ),
                    self._result(
                        f"mrr@{k}", mrr, details=details
                    ),
                ]
            )

        # Grounding cannot be inferred reliably from chunk IDs or
        # retrieval relevance. It needs supporting passages and a
        # claim-level or reference-based evaluation procedure.
        metrics.append(
            self._result(
                "answer_grounding",
                None,
                details={
                    "reason": (
                        "Grounding evaluation requires answer claims "
                        "and supporting source passages."
                    )
                },
            )
        )

        if not relevant:
            notes.append(
                "No relevant chunk IDs were supplied; recall, "
                "hit rate, and MRR are undefined."
            )

        if case.generated_answer is not None:
            notes.append(
                "Generated answer provided, but answer grounding "
                "has not yet been evaluated."
            )

        return EvaluationReport(
            case_id=case.case_id,
            evaluator="rag",
            metrics=metrics,
            notes=notes,
        )
