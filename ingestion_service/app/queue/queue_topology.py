import pika

from app.config.settings import settings


class QueueTopology:
    """
    Declares the RabbitMQ queues required by the ingestion pipeline.

    Queues:
    - article.processing
    - article.processing.retry
    - article.processing.dlq

    All queues are durable so they survive RabbitMQ restarts.
    """

    def __init__(
        self,
        rabbitmq_url: str | None = None,
        article_queue: str | None = None,
        retry_queue: str | None = None,
        dlq: str | None = None,
    ):
        self.rabbitmq_url = (
            rabbitmq_url
            if rabbitmq_url is not None
            else settings.RABBITMQ_URL
        )

        self.article_queue = (
            article_queue
            if article_queue is not None
            else settings.ARTICLE_QUEUE
        )

        self.retry_queue = (
            retry_queue
            if retry_queue is not None
            else settings.ARTICLE_RETRY_QUEUE
        )

        self.dlq = (
            dlq
            if dlq is not None
            else settings.ARTICLE_DLQ
        )

    def _create_connection(self):
        """
        Create a RabbitMQ connection.
        """

        if not self.rabbitmq_url:
            raise ValueError(
                "RABBITMQ_URL is not configured."
            )

        parameters = pika.URLParameters(
            self.rabbitmq_url
        )

        return pika.BlockingConnection(parameters)

    def declare(self) -> None:
        """
        Declare all queues required by the ingestion pipeline.

        The operation is idempotent:
        calling it multiple times will not create duplicate queues.
        """

        connection = self._create_connection()

        try:
            channel = connection.channel()

            self._declare_queue(
                channel,
                self.article_queue,
            )

            self._declare_queue(
                channel,
                self.retry_queue,
            )

            self._declare_queue(
                channel,
                self.dlq,
            )

        finally:
            connection.close()

    @staticmethod
    def _declare_queue(
        channel,
        queue_name: str,
    ) -> None:
        """
        Declare a single durable queue.
        """

        channel.queue_declare(
            queue=queue_name,
            durable=True,
        )