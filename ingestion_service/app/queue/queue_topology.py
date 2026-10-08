import pika

from app.config.settings import settings


class QueueTopology:
    """
    Declare durable work queues, fixed-delay retry queues,
    and dead-letter queues for both article and document ingestion.

    Article queues:
        article.processing
        article.processing.retry.1/.2/.3
        article.processing.dlq

        article.embedding
        article.embedding.retry.1/.2/.3
        article.embedding.dlq

    Document queues:
        document.embedding
        document.embedding.retry.1/.2/.3
        document.embedding.dlq

    Document parsing/chunking remains synchronous for now, so there
    is intentionally no document.processing queue yet.
    """

    def __init__(
        self,
        rabbitmq_url: str | None = None,
        article_queue: str | None = None,
        retry_queue: str | None = None,
        dlq: str | None = None,
        embedding_queue: str | None = None,
        embedding_retry_queue: str | None = None,
        embedding_dlq: str | None = None,
        document_embedding_queue: str | None = None,
        document_embedding_retry_queue: str | None = None,
        document_embedding_dlq: str | None = None,
        retry_delays_ms: tuple[int, ...] | None = None,
    ):
        self.rabbitmq_url = (
            rabbitmq_url
            if rabbitmq_url is not None
            else settings.RABBITMQ_URL
        )

        # ------------------------------------------------------
        # Article queues
        # ------------------------------------------------------

        self.article_queue = (
            article_queue
            or settings.ARTICLE_QUEUE
        )

        self.retry_queue = (
            retry_queue
            or settings.ARTICLE_RETRY_QUEUE
        )

        self.dlq = (
            dlq
            or settings.ARTICLE_DLQ
        )

        self.embedding_queue = (
            embedding_queue
            or settings.ARTICLE_EMBEDDING_QUEUE
        )

        self.embedding_retry_queue = (
            embedding_retry_queue
            or settings.ARTICLE_EMBEDDING_RETRY_QUEUE
        )

        self.embedding_dlq = (
            embedding_dlq
            or settings.ARTICLE_EMBEDDING_DLQ
        )

        # ------------------------------------------------------
        # Document embedding queues
        #
        # getattr() gives us safe defaults until these values are
        # explicitly added to settings.py.
        # ------------------------------------------------------

        self.document_embedding_queue = (
            document_embedding_queue
            or getattr(
                settings,
                "DOCUMENT_EMBEDDING_QUEUE",
                "document.embedding",
            )
        )

        self.document_embedding_retry_queue = (
            document_embedding_retry_queue
            or getattr(
                settings,
                "DOCUMENT_EMBEDDING_RETRY_QUEUE",
                "document.embedding.retry",
            )
        )

        self.document_embedding_dlq = (
            document_embedding_dlq
            or getattr(
                settings,
                "DOCUMENT_EMBEDDING_DLQ",
                "document.embedding.dlq",
            )
        )

        # ------------------------------------------------------
        # Shared retry policy
        #
        # Existing article retry delays are reused:
        # retry.1 -> 30 sec
        # retry.2 -> 2 min
        # retry.3 -> 10 min
        # ------------------------------------------------------

        self.retry_delays_ms = (
            retry_delays_ms
            if retry_delays_ms is not None
            else settings.ARTICLE_RETRY_DELAYS_MS
        )

        if (
            not self.retry_delays_ms
            or any(
                delay <= 0
                for delay in self.retry_delays_ms
            )
        ):
            raise ValueError(
                "Retry delays must be positive milliseconds."
            )

    def _create_connection(self):
        if not self.rabbitmq_url:
            raise ValueError(
                "RABBITMQ_URL is not configured."
            )

        return pika.BlockingConnection(
            pika.URLParameters(
                self.rabbitmq_url
            )
        )

    def declare(self) -> None:
        """
        Declare the complete Finzer RabbitMQ topology.

        Safe to call repeatedly as long as existing queue
        arguments match the definitions below.
        """

        connection = self._create_connection()

        try:
            channel = connection.channel()

            # ==================================================
            # Article processing
            # ==================================================

            self._declare_queue(
                channel,
                self.article_queue,
            )

            self._declare_queue(
                channel,
                self.dlq,
            )

            self._declare_retry_queues(
                channel,
                self.retry_queue,
                self.article_queue,
            )

            # ==================================================
            # Article embedding
            # ==================================================

            self._declare_queue(
                channel,
                self.embedding_queue,
            )

            self._declare_queue(
                channel,
                self.embedding_dlq,
            )

            self._declare_retry_queues(
                channel,
                self.embedding_retry_queue,
                self.embedding_queue,
            )

            # ==================================================
            # Document embedding
            # ==================================================

            self._declare_queue(
                channel,
                self.document_embedding_queue,
            )

            self._declare_queue(
                channel,
                self.document_embedding_dlq,
            )

            self._declare_retry_queues(
                channel,
                self.document_embedding_retry_queue,
                self.document_embedding_queue,
            )

        finally:
            connection.close()

    @staticmethod
    def _declare_queue(
        channel,
        queue_name: str,
    ) -> None:
        """
        Declare a durable RabbitMQ queue.
        """

        channel.queue_declare(
            queue=queue_name,
            durable=True,
        )

    def _declare_retry_queues(
        self,
        channel,
        retry_queue_prefix: str,
        return_queue: str,
    ) -> None:
        """
        Declare numbered fixed-delay retry queues.

        Example:

            document.embedding.retry.1
                TTL 30 sec
                    ↓
            document.embedding

            document.embedding.retry.2
                TTL 2 min
                    ↓
            document.embedding

            document.embedding.retry.3
                TTL 10 min
                    ↓
            document.embedding

        RabbitMQ automatically returns expired retry messages to
        the original work queue through dead-letter routing.
        """

        for attempt, delay_ms in enumerate(
            self.retry_delays_ms,
            start=1,
        ):
            channel.queue_declare(
                queue=(
                    f"{retry_queue_prefix}."
                    f"{attempt}"
                ),
                durable=True,
                arguments={
                    "x-message-ttl": delay_ms,
                    "x-dead-letter-exchange": "",
                    "x-dead-letter-routing-key": (
                        return_queue
                    ),
                },
            )