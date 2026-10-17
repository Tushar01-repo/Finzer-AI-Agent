from app.reliability.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerPolicy,
    CircuitOpenError,
)

breaker = CircuitBreaker(
    CircuitBreakerPolicy(
        failure_threshold=2,
        recovery_timeout_seconds=0,
    )
)

def failing_service():
    raise ConnectionError("Service unavailable")

for _ in range(2):
    try:
        breaker.call(failing_service)
    except ConnectionError:
        pass

print("After failures:", breaker.state.value)

try:
    breaker.call(lambda: "recovered")
    print("After recovery:", breaker.state.value)
except CircuitOpenError:
    print("Circuit blocked the call")