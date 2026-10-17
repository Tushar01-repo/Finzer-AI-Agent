
from app.evaluation.models import RAGEvaluationCase, RetrievalItem
from app.evaluation.rag_evaluator import RAGEvaluator

case = RAGEvaluationCase(
    case_id="rag-001",
    query="What is the latest financial news about Infosys?",
    relevant_chunk_ids={"chunk-1", "chunk-3"},
    retrieved=[
        RetrievalItem(chunk_id="chunk-1", rank=1, score=0.95),
        RetrievalItem(chunk_id="chunk-2", rank=2, score=0.80),
        RetrievalItem(chunk_id="chunk-3", rank=3, score=0.75),
    ],
)

report = RAGEvaluator(k_values=(1, 3, 5)).evaluate(case)

for metric in report.metrics:
    print(f"{metric.name}: {metric.value}")
