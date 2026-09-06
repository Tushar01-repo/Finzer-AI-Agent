import json
from typing import Any

import pika

from app.config.settings import settings


class QueuePublisher:
    """
    Publishes article-processing messages to RabbitMQ.
    """

    def __init__(
        self,
        rabbitmq_url: str | None = None,
        queue_name: str | None = None,
    ):
        self.rabbitmq_url = (
            rabbitmq_url
            if rabbitmq_url is not None
            else settings.RABBITMQ_URL
        )

        self.queue_name = (
            queue_name
            if queue_name is not None
            else settings.ARTICLE_QUEUE
        )

    def _create_connection(self):
        if not self.rabbitmq_url:
            raise ValueError(
                "RABBITMQ_URL is not configured."
            )

        parameters = pika.URLParameters(
            self.rabbitmq_url
        )

        return pika.BlockingConnection(parameters)

    def publish(self, message: dict[str, Any]) -> None:
        """
        Publish a message to the article-processing queue.
        """

        connection = self._create_connection()

        try:
            channel = connection.channel()

            channel.queue_declare(
                queue=self.queue_name,
                durable=True,
            )

            channel.basic_publish(
                exchange="",
                routing_key=self.queue_name,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                ),
            )

        finally:
            connection.close()