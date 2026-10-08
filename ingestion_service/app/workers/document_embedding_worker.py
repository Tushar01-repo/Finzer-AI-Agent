import json
import signal
from typing import Any

import pika

from app.clients.embedding_router import EmbeddingRouter
from app.config.settings import settings
from app.queue.queue_topology import QueueTopology
from app.queue.retry_router import RetryRouter
from app.repositories.database import PostgresDatabase
from app.repositories.document_repository import DocumentRepository


class DocumentEmbeddingWorker:
    """
    Consume document.embedding messages, retrieve the authoritative
    chunk content from PostgreSQL, generate an embedding through the
    existing EmbeddingRouter, and persist it in pgvector.

    RabbitMQ message format:

        {
            "chunk_id": 123
        }

    The embedding provider/model is locked for the lifetime of the
    worker session by EmbeddingRouter, matching the article embedding
    worker behaviour.
    """

    def __init__(
        self,
        rabbitmq_url: str | None = None,
        queue_name: str | None = None,
    ):
        # ------------------------------------------------------
        # RabbitMQ
        # ------------------------------------------------------

        self.rabbitmq_url = (
            rabbitmq_url
            or settings.RABBITMQ_URL
        )

        self.queue_name = (
            queue_name
            or getattr(
                settings,
                "DOCUMENT_EMBEDDING_QUEUE",
                "document.embedding",
            )
        )

        self.retry_queue_prefix = getattr(
            settings,
            "DOCUMENT_EMBEDDING_RETRY_QUEUE",
            "document.embedding.retry",
        )

        self.dlq = getattr(
            settings,
            "DOCUMENT_EMBEDDING_DLQ",
            "document.embedding.dlq",
        )

        # ------------------------------------------------------
        # Embedding configuration
        # ------------------------------------------------------

        self.embedding_dimension = (
            settings.EMBEDDING_DIMENSION
        )

        if not self.rabbitmq_url:
            raise ValueError(
                "RABBITMQ_URL is not configured."
            )

        if not self.queue_name:
            raise ValueError(
                "DOCUMENT_EMBEDDING_QUEUE "
                "is not configured."
            )

        if self.embedding_dimension <= 0:
            raise ValueError(
                "EMBEDDING_DIMENSION must be "
                "greater than zero."
            )

        if self.embedding_dimension != 1024:
            raise ValueError(
                "Document embeddings currently require "
                "EMBEDDING_DIMENSION=1024 because "
                "document_chunk_embeddings.embedding "
                "is VECTOR(1024)."
            )

        # ------------------------------------------------------
        # Retry routing
        # ------------------------------------------------------

        self.retry_router = RetryRouter(
            retry_queue_prefix=(
                self.retry_queue_prefix
            ),
            dlq=self.dlq,
            retry_delays_ms=(
                settings.ARTICLE_RETRY_DELAYS_MS
            ),
        )

        # ------------------------------------------------------
        # Embedding provider
        #
        # EmbeddingRouter selects/locks provider + model for
        # this worker session.
        # ------------------------------------------------------

        self.embedding_client = (
            EmbeddingRouter()
        )

        self.embedding_model = (
            self.embedding_client.model
        )

        self.embedding_provider = (
            self.embedding_client.provider
        )

        # ------------------------------------------------------
        # PostgreSQL
        # ------------------------------------------------------

        self.database = PostgresDatabase()

        self.repository = (
            DocumentRepository(
                self.database
            )
        )

        # ------------------------------------------------------
        # Runtime state
        # ------------------------------------------------------

        self.connection: (
            pika.BlockingConnection | None
        ) = None

        self.channel = None

        self._stopping = False

    # ============================================================
    # RabbitMQ
    # ============================================================

    def _create_connection(
        self,
    ) -> pika.BlockingConnection:
        parameters = pika.URLParameters(
            self.rabbitmq_url
        )

        parameters.heartbeat = 600
        parameters.blocked_connection_timeout = 300

        return pika.BlockingConnection(
            parameters
        )

    # ============================================================
    # Message parsing
    # ============================================================

    @staticmethod
    def _parse_message(
        body: bytes,
    ) -> dict[str, Any]:
        try:
            message = json.loads(
                body.decode("utf-8")
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise ValueError(
                "Message is not valid JSON."
            ) from exc

        if not isinstance(message, dict):
            raise ValueError(
                "Message must be a JSON object."
            )

        chunk_id = message.get(
            "chunk_id"
        )

        # bool is technically an int in Python,
        # so reject it explicitly.
        if (
            isinstance(chunk_id, bool)
            or not isinstance(chunk_id, int)
            or chunk_id <= 0
        ):
            raise ValueError(
                "chunk_id must be a positive integer."
            )

        return {
            "chunk_id": chunk_id,
        }

    # ============================================================
    # Embedding
    # ============================================================

    def _generate_embedding(
        self,
        text: str,
    ) -> list[float]:
        return self.embedding_client.embed(
            text
        )

    # ============================================================
    # Safe RabbitMQ acknowledgement
    # ============================================================

    @staticmethod
    def _safe_ack(
        channel,
        delivery_tag,
    ) -> bool:
        if (
            channel is None
            or not channel.is_open
        ):
            print(
                "RabbitMQ channel is closed; "
                "message could not be ACKed."
            )
            return False

        try:
            channel.basic_ack(
                delivery_tag=delivery_tag
            )

            print(
                "RabbitMQ message ACKed."
            )

            return True

        except (
            pika.exceptions.AMQPError,
            OSError,
        ) as exc:
            print(
                f"RabbitMQ ACK failed: {exc}"
            )

            return False

    # ============================================================
    # Message processing
    # ============================================================

    def _on_message(
        self,
        channel,
        method,
        properties,
        body: bytes,
    ) -> None:
        delivery_tag = (
            method.delivery_tag
        )

        # ------------------------------------------------------
        # Parse message
        # ------------------------------------------------------

        try:
            message = self._parse_message(
                body
            )

            chunk_id = message[
                "chunk_id"
            ]

        except ValueError as exc:
            print(
                f"Invalid document embedding "
                f"message: {exc}"
            )

            outcome = (
                self.retry_router.route_failure(
                    channel,
                    delivery_tag=delivery_tag,
                    properties=properties,
                    body=body,
                    retryable=False,
                    error=exc,
                )
            )

            print(
                "Invalid message routed "
                f"to {outcome}."
            )

            return

        print("=" * 70)
        print(
            f"Embedding document chunk: "
            f"{chunk_id}"
        )

        try:
            # --------------------------------------------------
            # Fetch authoritative chunk from PostgreSQL.
            #
            # We ask specifically about the provider/model
            # locked by this worker session.
            # --------------------------------------------------

            chunk = (
                self.repository
                .get_embedding_input(
                    chunk_id,
                    provider=(
                        self.embedding_provider
                    ),
                    model=(
                        self.embedding_model
                    ),
                )
            )

            # --------------------------------------------------
            # Chunk was deleted / replaced after message was
            # published.
            #
            # This is not retryable. The queue message is stale.
            # --------------------------------------------------

            if chunk is None:
                print(
                    "Chunk does not exist in "
                    "PostgreSQL. ACKing stale "
                    "message."
                )

                self._safe_ack(
                    channel,
                    delivery_tag,
                )

                return

            print(
                f"Document: "
                f"{chunk['document_key']}"
            )

            print(
                f"Chunk index: "
                f"{chunk['chunk_index']}"
            )

            print(
                f"Content type: "
                f"{chunk['content_type']}"
            )

            print(
                f"Pages: "
                f"{chunk['page_start']}"
                f"-{chunk['page_end']}"
            )

            print(
                f"Token count: "
                f"{chunk['token_count']}"
            )

            # --------------------------------------------------
            # Idempotency
            # --------------------------------------------------

            if chunk["has_embedding"]:
                print(
                    "Chunk already has an embedding "
                    "for this provider/model. "
                    "ACKing duplicate message."
                )

                self._safe_ack(
                    channel,
                    delivery_tag,
                )

                return

            # --------------------------------------------------
            # Validate content
            # --------------------------------------------------

            text = (
                chunk["content"]
                or ""
            ).strip()

            if not text:
                raise ValueError(
                    "Document chunk has no usable "
                    "text for embedding."
                )

            print(
                f"Embedding input length: "
                f"{len(text)}"
            )

            print(
                "Sending chunk to "
                f"{self.embedding_provider} "
                "embeddings..."
            )

            # --------------------------------------------------
            # Generate embedding
            # --------------------------------------------------

            embedding = (
                self._generate_embedding(
                    text
                )
            )

            print(
                f"Embedding dimension: "
                f"{len(embedding)}"
            )

            if (
                len(embedding)
                != self.embedding_dimension
            ):
                raise ValueError(
                    "Unexpected embedding dimension: "
                    f"expected "
                    f"{self.embedding_dimension}, "
                    f"got {len(embedding)}."
                )

            # --------------------------------------------------
            # Persist
            # --------------------------------------------------

            self.repository.save_embedding(
                chunk_id=chunk_id,
                embedding=embedding,
                provider=(
                    self.embedding_provider
                ),
                model=(
                    self.embedding_model
                ),
                expected_dimension=(
                    self.embedding_dimension
                ),
            )

            print(
                "Embedding saved to PostgreSQL."
            )

            # --------------------------------------------------
            # Document-level status
            #
            # This changes the document to embedded only when
            # every chunk has an embedding for this exact
            # provider/model.
            # --------------------------------------------------

            document_complete = (
                self.repository
                .mark_document_embedded_if_complete(
                    document_key=(
                        chunk["document_key"]
                    ),
                    provider=(
                        self.embedding_provider
                    ),
                    model=(
                        self.embedding_model
                    ),
                )
            )

            if document_complete:
                print(
                    "All document chunks embedded."
                )

                print(
                    "Document status: embedded"
                )

            else:
                print(
                    "Document still has chunks "
                    "waiting for embeddings."
                )

            # --------------------------------------------------
            # ACK only after PostgreSQL persistence succeeds
            # --------------------------------------------------

            self._safe_ack(
                channel,
                delivery_tag,
            )

        except Exception as exc:
            print(
                "Document embedding processing "
                f"failed: {exc}"
            )

            outcome = (
                self.retry_router.route_failure(
                    channel,
                    delivery_tag=delivery_tag,
                    properties=properties,
                    body=body,
                    retryable=True,
                    error=exc,
                )
            )

            print(
                "Embedding failure routed "
                f"to {outcome}."
            )

        finally:
            print()

    # ============================================================
    # Signals
    # ============================================================

    def _register_signal_handlers(
        self,
    ) -> None:
        signal.signal(
            signal.SIGINT,
            self._handle_signal,
        )

        signal.signal(
            signal.SIGTERM,
            self._handle_signal,
        )

    def _handle_signal(
        self,
        signum,
        frame,
    ) -> None:
        print(
            f"Received signal {signum}; "
            "stopping document embedding "
            "worker..."
        )

        self.stop()

    # ============================================================
    # Worker lifecycle
    # ============================================================

    def start(
        self,
    ) -> None:
        print("=" * 70)
        print(
            "Finzer Document Embedding Worker"
        )
        print("=" * 70)

        print(
            f"Queue: {self.queue_name}"
        )

        print(
            "Embedding provider: "
            f"{self.embedding_provider} "
            "(session locked)"
        )

        print(
            f"Model: "
            f"{self.embedding_model}"
        )

        print(
            f"Dimension: "
            f"{self.embedding_dimension}"
        )

        print()

        # ------------------------------------------------------
        # Declare topology first.
        #
        # Important: QueueTopology creates its own connection,
        # so do this before opening the consumer connection.
        # ------------------------------------------------------

        QueueTopology(
            rabbitmq_url=(
                self.rabbitmq_url
            )
        ).declare()

        # ------------------------------------------------------
        # Consumer connection
        # ------------------------------------------------------

        self.connection = (
            self._create_connection()
        )

        self.channel = (
            self.connection.channel()
        )

        self.channel.confirm_delivery()

        self.channel.queue_declare(
            queue=self.queue_name,
            durable=True,
        )

        # One chunk at a time per worker process.
        self.channel.basic_qos(
            prefetch_count=1
        )

        self.channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=(
                self._on_message
            ),
            auto_ack=False,
        )

        self._register_signal_handlers()

        print(
            "Waiting for document "
            "embedding messages..."
        )

        print(
            "Press CTRL+C to stop."
        )

        print()

        try:
            self.channel.start_consuming()

        except KeyboardInterrupt:
            self.stop()

        except pika.exceptions.AMQPError as exc:
            print(
                "RabbitMQ consumer connection "
                f"failed: {exc}"
            )

        finally:
            self.stop()

    def stop(
        self,
    ) -> None:
        if self._stopping:
            return

        self._stopping = True

        print(
            "Stopping document embedding "
            "worker..."
        )

        try:
            if (
                self.channel is not None
                and self.channel.is_open
            ):
                if getattr(
                    self.channel,
                    "is_consuming",
                    False,
                ):
                    self.channel.stop_consuming()

        except (
            pika.exceptions.AMQPError,
            OSError,
        ):
            pass

        try:
            if (
                self.connection is not None
                and self.connection.is_open
            ):
                self.connection.close()

        except (
            pika.exceptions.AMQPError,
            OSError,
        ):
            pass

        print(
            "Document embedding worker stopped."
        )


def main() -> None:
    worker = DocumentEmbeddingWorker()
    worker.start()


if __name__ == "__main__":
    main()