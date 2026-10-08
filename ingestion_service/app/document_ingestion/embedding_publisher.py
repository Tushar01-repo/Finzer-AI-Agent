from __future__ import annotations

from typing import Any

from app.config.settings import settings
# from app.messaging.queue_publisher import QueuePublisher
from app.queue.queue_publisher import QueuePublisher
from app.repositories.database import PostgresDatabase
from app.repositories.document_repository import DocumentRepository


class DocumentEmbeddingPublisher:
    """
    Publishes document chunks to the document embedding queue.

    Responsibilities:
    - Resolve all chunks belonging to one document.
    - Publish one lightweight RabbitMQ message per chunk.
    - Keep embedding generation out of the ingestion process.

    The embedding worker is responsible for:
    - selecting/locking the embedding provider
    - checking provider/model-specific idempotency
    - generating embeddings
    - persisting vectors
    - marking the document embedded when complete
    """

    def __init__(
        self,
        *,
        database: PostgresDatabase | None = None,
        publisher: QueuePublisher | None = None,
        queue_name: str | None = None,
    ):
        self.database = database or PostgresDatabase()

        self.repository = DocumentRepository(
            self.database
        )

        self.queue_name = (
            queue_name
            or getattr(
                settings,
                "DOCUMENT_EMBEDDING_QUEUE",
                "document.embedding",
            )
        )

        self.publisher = (
            publisher
            or QueuePublisher(
                queue_name=self.queue_name
            )
        )

    def publish_document(
        self,
        document_key: str,
    ) -> dict[str, Any]:
        """
        Publish every chunk belonging to one document.

        Messages contain only:

            {
                "chunk_id": <int>
            }

        Provider/model-specific duplicate protection is intentionally
        handled by the embedding worker.
        """

        if not document_key:
            raise ValueError(
                "document_key cannot be empty."
            )

        document = self.repository.get_by_key(
            document_key
        )

        if document is None:
            raise KeyError(
                "Document not found for "
                f"document_key={document_key}"
            )

        chunks = self.repository.get_chunks_for_document(
            document_key
        )

        if not chunks:
            raise RuntimeError(
                "Document has no chunks to publish. "
                f"document_key={document_key}"
            )

        published = 0

        for chunk in chunks:
            chunk_id = int(
                chunk["chunk_id"]
            )

            self.publisher.publish(
                {
                    "chunk_id": chunk_id,
                }
            )

            published += 1

        # The document now has asynchronous embedding work scheduled.
        self.repository.mark_document_embedding(
            document_key
        )

        return {
            "document_key": document_key,
            "document_id": document["document_id"],
            "queue": self.queue_name,
            "total_chunks": len(chunks),
            "published": published,
        }