import pika


class RetryRouter:
    """Route a failed delivery to a bounded retry queue or final DLQ."""

    def __init__(self, *, retry_queue_prefix: str, dlq: str, retry_delays_ms: tuple[int, ...]):
        if not retry_delays_ms or any(delay <= 0 for delay in retry_delays_ms):
            raise ValueError("retry_delays_ms must contain positive values.")
        self.retry_queue_prefix = retry_queue_prefix
        self.dlq = dlq
        self.retry_delays_ms = retry_delays_ms

    @staticmethod
    def _headers(properties) -> dict:
        return dict(getattr(properties, "headers", None) or {})

    @staticmethod
    def _properties(properties, headers: dict) -> pika.BasicProperties:
        return pika.BasicProperties(
            content_type=getattr(properties, "content_type", None) or "application/json",
            content_encoding=getattr(properties, "content_encoding", None),
            headers=headers,
            delivery_mode=2,
            correlation_id=getattr(properties, "correlation_id", None),
            message_id=getattr(properties, "message_id", None),
            timestamp=getattr(properties, "timestamp", None),
            type=getattr(properties, "type", None),
            app_id=getattr(properties, "app_id", None),
        )

    def route_failure(self, channel, *, delivery_tag, properties, body: bytes, retryable: bool, error: Exception) -> str:
        headers = self._headers(properties)
        completed_retries = int(headers.get("x-retry-count", 0))
        headers["x-last-error"] = str(error)[:500]

        if retryable and completed_retries < len(self.retry_delays_ms):
            next_attempt = completed_retries + 1
            headers["x-retry-count"] = next_attempt
            destination = f"{self.retry_queue_prefix}.{next_attempt}"
            outcome = "retry"
        else:
            headers["x-retry-count"] = completed_retries
            headers["x-final-failure"] = True
            destination = self.dlq
            outcome = "dlq"

        channel.basic_publish(
            exchange="",
            routing_key=destination,
            body=body,
            properties=self._properties(properties, headers),
            mandatory=True,
        )
        channel.basic_ack(delivery_tag=delivery_tag)
        return outcome
