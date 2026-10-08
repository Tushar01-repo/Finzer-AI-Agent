from app.document_ingestion.embedding_publisher import (
    DocumentEmbeddingPublisher,
)


DOCUMENT_KEY = (
    "3adccc083d26e3b574fb187d92c87e80"
    "be56adee2060c285eb45049c5dae85b5"
)


def main():
    print("=" * 70)
    print("Finzer - Publish Document Embedding Jobs")
    print("=" * 70)

    publisher = DocumentEmbeddingPublisher()

    print(f"\nDocument key:\n{DOCUMENT_KEY}\n")

    result = publisher.publish_document(
        DOCUMENT_KEY
    )

    print("Publishing completed.")
    print()
    print(
        f"document_id = {result['document_id']}"
    )
    print(
        f"queue       = {result['queue']}"
    )
    print(
        f"chunks      = {result['total_chunks']}"
    )
    print(
        f"published   = {result['published']}"
    )

    print("\n" + "=" * 70)
    print("DOCUMENT EMBEDDING JOBS PUBLISHED")
    print("=" * 70)


if __name__ == "__main__":
    main()