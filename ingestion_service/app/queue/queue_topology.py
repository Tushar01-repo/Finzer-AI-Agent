# import pika

# from app.config.settings import settings


# class QueueTopology:
#     """
#     Declares the RabbitMQ queues required by the ingestion pipeline.

#     Queues:
#     - article.processing
#     - article.processing.retry
#     - article.processing.dlq
#     - article.embedding

#     All queues are durable so they survive RabbitMQ restarts.
#     """

#     def __init__(
#         self,
#         rabbitmq_url: str | None = None,
#         article_queue: str | None = None,
#         retry_queue: str | None = None,
#         dlq: str | None = None,
#         embedding_queue: str | None = None,
#     ):
#         self.rabbitmq_url = (
#             rabbitmq_url
#             if rabbitmq_url is not None
#             else settings.RABBITMQ_URL
#         )

#         self.article_queue = (
#             article_queue
#             if article_queue is not None
#             else settings.ARTICLE_QUEUE
#         )

#         self.retry_queue = (
#             retry_queue
#             if retry_queue is not None
#             else settings.ARTICLE_RETRY_QUEUE
#         )

#         self.dlq = (
#             dlq
#             if dlq is not None
#             else settings.ARTICLE_DLQ
#         )

#         self.embedding_queue = (
#             embedding_queue
#             if embedding_queue is not None
#             else settings.ARTICLE_EMBEDDING_QUEUE
#         )

#     def _create_connection(self):
#         """
#         Create a RabbitMQ connection.
#         """

#         if not self.rabbitmq_url:
#             raise ValueError(
#                 "RABBITMQ_URL is not configured."
#             )

#         parameters = pika.URLParameters(
#             self.rabbitmq_url
#         )

#         return pika.BlockingConnection(parameters)

#     def declare(self) -> None:
#         """
#         Declare all queues required by the ingestion pipeline.

#         The operation is idempotent:
#         calling it multiple times will not create duplicate queues.
#         """

#         connection = self._create_connection()

#         try:
#             channel = connection.channel()

#             self._declare_queue(
#                 channel,
#                 self.article_queue,
#             )

#             self._declare_queue(
#                 channel,
#                 self.retry_queue,
#             )

#             self._declare_queue(
#                 channel,
#                 self.dlq,
#             )

#             self._declare_queue(
#                 channel,
#                 self.embedding_queue,
#             )

#         finally:
#             connection.close()

#     @staticmethod
#     def _declare_queue(
#         channel,
#         queue_name: str,
#     ) -> None:
#         """
#         Declare a single durable queue.
#         """

#         channel.queue_declare(
#             queue=queue_name,
#             durable=True,
#         )


import pika

from app.config.settings import settings


class QueueTopology:
    """Declare durable work, fixed-delay retry, and dead-letter queues."""

    def __init__(
        self,
        rabbitmq_url: str | None = None,
        article_queue: str | None = None,
        retry_queue: str | None = None,
        dlq: str | None = None,
        embedding_queue: str | None = None,
        embedding_retry_queue: str | None = None,
        embedding_dlq: str | None = None,
        retry_delays_ms: tuple[int, ...] | None = None,
    ):
        self.rabbitmq_url = rabbitmq_url if rabbitmq_url is not None else settings.RABBITMQ_URL
        self.article_queue = article_queue or settings.ARTICLE_QUEUE
        self.retry_queue = retry_queue or settings.ARTICLE_RETRY_QUEUE
        self.dlq = dlq or settings.ARTICLE_DLQ
        self.embedding_queue = embedding_queue or settings.ARTICLE_EMBEDDING_QUEUE
        self.embedding_retry_queue = embedding_retry_queue or settings.ARTICLE_EMBEDDING_RETRY_QUEUE
        self.embedding_dlq = embedding_dlq or settings.ARTICLE_EMBEDDING_DLQ
        self.retry_delays_ms = retry_delays_ms if retry_delays_ms is not None else settings.ARTICLE_RETRY_DELAYS_MS
        if not self.retry_delays_ms or any(delay <= 0 for delay in self.retry_delays_ms):
            raise ValueError("Retry delays must be positive milliseconds.")

    def _create_connection(self):
        if not self.rabbitmq_url:
            raise ValueError("RABBITMQ_URL is not configured.")
        return pika.BlockingConnection(pika.URLParameters(self.rabbitmq_url))

    def declare(self) -> None:
        connection = self._create_connection()
        try:
            channel = connection.channel()
            self._declare_queue(channel, self.article_queue)
            self._declare_queue(channel, self.dlq)
            self._declare_queue(channel, self.embedding_queue)
            self._declare_queue(channel, self.embedding_dlq)
            self._declare_retry_queues(channel, self.retry_queue, self.article_queue)
            self._declare_retry_queues(channel, self.embedding_retry_queue, self.embedding_queue)
        finally:
            connection.close()

    @staticmethod
    def _declare_queue(channel, queue_name: str) -> None:
        channel.queue_declare(queue=queue_name, durable=True)

    def _declare_retry_queues(self, channel, retry_queue_prefix: str, return_queue: str) -> None:
        for attempt, delay_ms in enumerate(self.retry_delays_ms, start=1):
            channel.queue_declare(
                queue=f"{retry_queue_prefix}.{attempt}",
                durable=True,
                arguments={
                    "x-message-ttl": delay_ms,
                    "x-dead-letter-exchange": "",
                    "x-dead-letter-routing-key": return_queue,
                },
            )
