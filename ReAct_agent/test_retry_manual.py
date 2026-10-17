from app.reliability.retry import (
    RetryPolicy,
    RetryNotAllowedError,
    retry_call,
)

attempts = 0


def temporary_failure():
    global attempts
    attempts += 1

    if attempts < 3:
        raise ConnectionError("Temporary connection failure")

    return {"status": "success"}


result = retry_call(
    temporary_failure,
    retry_safe=True,  # Only for confirmed retry-safe operations
    policy=RetryPolicy(
        max_attempts=3,
        initial_delay_seconds=0.01,
        max_delay_seconds=0.1,
        jitter_ratio=0,
    ),
)

print("Result:", result)
print("Attempts:", attempts)

try:
    retry_call(
        lambda: print("WRITE EXECUTED"),
        retry_safe=False,
    )
except RetryNotAllowedError:
    print("Unsafe write retry blocked")