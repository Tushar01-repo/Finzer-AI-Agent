import json
import time

from app.observability.metrics import metrics

metrics.reset()

with metrics.time_operation("agent"):
    time.sleep(0.05)

with metrics.time_operation("rag"):
    time.sleep(0.02)

metrics.record_operation("mcp", "success")
metrics.record_operation("mcp", "error")

metrics.record_llm_usage(
    input_tokens=1500,
    output_tokens=500,
    input_cost_per_million_usd=0.25,
    output_cost_per_million_usd=2.00,
)

print(json.dumps(metrics.snapshot(), indent=2))