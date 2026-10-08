import json

import pika

from app.clients.embedding_router import EmbeddingRouter
from app.config.settings import settings
from app.repositories.database import PostgresDatabase
from app.repositories.document_repository import DocumentRepository


QUEUE_NAME = "document.embedding"


def main():
    print("=" * 70)
    print("Finzer - Publish One Document Chunk")
    print("=" * 70)

    # ----------------------------------------------------------
    # 1. Determine the provider/model that the worker will use.
    #
    # This matters because pending-embedding lookup is scoped to
    # the exact provider/model.
    # ----------------------------------------------------------

    print("\n[1] Resolving embedding provider...")

    embedding_router = EmbeddingRouter()

    provider = embedding_router.provider
    model = embedding_router.model

    print(f"    provider = {provider}")
    print(f"    model    = {model}")

    # ----------------------------------------------------------
    # 2. Find one real chunk pending embedding
    # ----------------------------------------------------------

    print("\n[2] Looking for one pending document chunk...")

    database = PostgresDatabase()

    repository = DocumentRepository(
        database
    )

    # chunks = repository.get_chunks_pending_embedding(
    #     provider=provider,
    #     model=model,
    #     limit=1,
    # )

    REAL_DOCUMENT_KEY = (
        "3adccc083d26e3b574fb187d92c87e80be56adee2060c285eb45049c5dae85b5"
    )

    all_pending_chunks = repository.get_chunks_pending_embedding(
        provider=provider,
        model=model,
        limit=1000,
    )

    chunks = [
        chunk
        for chunk in all_pending_chunks
        if chunk["document_key"] == REAL_DOCUMENT_KEY
    ][:1]

    if not chunks:
        print(
            "    No document chunks are pending "
            "embedding for this provider/model."
        )
        return

    chunk = chunks[0]

    chunk_id = chunk["chunk_id"]

    print(f"    chunk_id     = {chunk_id}")
    print(f"    document_key = {chunk['document_key']}")
    print(f"    chunk_index  = {chunk['chunk_index']}")
    print(f"    content_type = {chunk['content_type']}")
    print(f"    token_count  = {chunk['token_count']}")

    # ----------------------------------------------------------
    # 3. Publish ONLY the chunk ID
    # ----------------------------------------------------------

    message = {
        "chunk_id": chunk_id,
    }

    print("\n[3] Publishing RabbitMQ message...")
    print(f"    queue   = {QUEUE_NAME}")
    print(f"    message = {message}")

    if not settings.RABBITMQ_URL:
        raise ValueError(
            "RABBITMQ_URL is not configured."
        )

    connection = pika.BlockingConnection(
        pika.URLParameters(
            settings.RABBITMQ_URL
        )
    )

    try:
        channel = connection.channel()

        channel.queue_declare(
            queue=QUEUE_NAME,
            durable=True,
        )

        channel.confirm_delivery()

        published = channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
            mandatory=True,
        )

        if published is False:
            raise RuntimeError(
                "RabbitMQ did not confirm publication."
            )

        print("    Message published successfully.")

    finally:
        connection.close()

    # ----------------------------------------------------------
    # 4. Confirm queue contains our test message
    # ----------------------------------------------------------

    connection = pika.BlockingConnection(
        pika.URLParameters(
            settings.RABBITMQ_URL
        )
    )

    try:
        channel = connection.channel()

        result = channel.queue_declare(
            queue=QUEUE_NAME,
            passive=True,
        )

        print("\n[4] Queue state")

        print(
            f"    messages  = "
            f"{result.method.message_count}"
        )

        print(
            f"    consumers = "
            f"{result.method.consumer_count}"
        )

    finally:
        connection.close()

    print("\n" + "=" * 70)
    print("ONE DOCUMENT CHUNK PUBLISHED")
    print("=" * 70)

    print(
        "\nNow start document_embedding_worker.py "
        "in a separate terminal."
    )


if __name__ == "__main__":
    main()