from __future__ import annotations

import os

from app.agent.graph import ReActGraph
from app.agent.llm import OpenAIDecisionModel
from app.agent.state import AgentState
from app.tools.executor import FinzerToolExecutor
from app.tools.mcp_client import call_mcp_tool


def main() -> None:
    assert os.getenv("OPENAI_API_KEY"), (
        "OPENAI_API_KEY is not configured."
    )

    # 1. Live OpenAI decision model
    decision_model = OpenAIDecisionModel(
        model="gpt-4.1-mini",
        temperature=0.0,
    )

    # 2. Real MCP tool executor
    tool_executor = FinzerToolExecutor(
        mcp_call=call_mcp_tool,
    )

    # 3. ReAct orchestration
    graph = ReActGraph(
        decision_model=decision_model,
        tool_executor=tool_executor,
        max_steps=8,
        max_tool_calls=5,
    )

    # 4. User request
    state = AgentState(
        user_query=(
            "What is the current gold spot price "
            "per gram in INR? Use the gold price tool "
            "and give me the actual retrieved value."
        )
    )

    # 5. Execute the full ReAct loop
    result = graph.run(state)

    # 6. Inspect results
    print("\n" + "=" * 70)
    print("FINZER REACT AGENT - LIVE GOLD MCP E2E TEST")
    print("=" * 70)

    print("\nExecution status:", result.execution_status)
    print("Next action:", result.next_action)
    print("Steps:", result.step_count)
    print("Tool calls:", result.tool_call_count)

    print("\nTool observations:")
    for observation in result.observations:
        print(observation.model_dump(mode="json"))

    print("\nErrors:")
    for error in result.errors:
        print(error.model_dump(mode="json"))

    print("\nFinal answer:")
    print(result.final_answer)


    # 7. Integration assertions

    assert result.tool_call_count >= 1, (
        "Agent did not invoke any tools."
    )

    assert result.observations, (
        "No tool observations were recorded."
    )

    # Verify Gold MCP returned an actual price
    assert any(
        observation.tool_name == "gold_spot_price"
        and observation.status.value == "success"
        and observation.data is not None
        and observation.data.get("status") == "success"
        and observation.data.get("data", {}).get(
            "price_per_gram", 0
        ) > 0
        for observation in result.observations
    ), "Gold MCP tool did not return a successful price"

    assert result.final_answer, (
        "Agent did not produce a final answer."
    )

    print("\nPASS - Full ReAct + Gold MCP integration")



if __name__ == "__main__":
    main()