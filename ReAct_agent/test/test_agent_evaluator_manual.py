
from app.evaluation.models import AgentEvaluationCase
from app.evaluation.agent_evaluator import AgentEvaluator

case = AgentEvaluationCase(
    case_id="agent-001",
    user_request="Find recent Infosys financial news",
    expected_tool_names=["search_news", "retrieve_articles"],
    actual_tool_names=["search_news", "retrieve_articles"],
    expected_final_status="completed",
    actual_final_status="completed",
    expected_approval_required=False,
    actual_approval_required=False,
    task_completed=True,
)

report = AgentEvaluator().evaluate(case)

for metric in report.metrics:
    print(f"{metric.name}: {metric.value}")
