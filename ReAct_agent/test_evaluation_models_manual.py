
from app.evaluation.models import (
    RAGEvaluationCase,
    RetrievalItem,
    AgentEvaluationCase,
)

rag_case = RAGEvaluationCase(
    case_id="rag-001",
    query="What is the latest financial news about Infosys?",
    relevant_chunk_ids={"chunk-1", "chunk-3"},
    retrieved=[
        RetrievalItem(chunk_id="chunk-1", rank=1, score=0.95),
        RetrievalItem(chunk_id="chunk-2", rank=2, score=0.80),
        RetrievalItem(chunk_id="chunk-3", rank=3, score=0.75),
    ],
)

agent_case = AgentEvaluationCase(
    case_id="agent-001",
    user_request="Find recent Infosys news",
    expected_tool_names=["search_news"],
    actual_tool_names=["search_news"],
    expected_final_status="completed",
    actual_final_status="completed",
    task_completed=True,
)

print("RAG case:", rag_case.case_id)
print("Retrieved chunks:", len(rag_case.retrieved))
print("Agent case:", agent_case.case_id)
print("Task completed:", agent_case.task_completed)
