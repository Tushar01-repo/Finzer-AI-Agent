from app.repositories.database import PostgresDatabase


DOCUMENT_KEY = (
    "3adccc083d26e3b574fb187d92c87e80"
    "be56adee2060c285eb45049c5dae85b5"
)

PROVIDER = "openai"
MODEL = "text-embedding-3-small"
EXPECTED_DIMENSION = 1024
EXPECTED_CHUNKS = 30


def main():
    print("=" * 70)
    print("Finzer - Full Document Embedding Verification")
    print("=" * 70)

    db = PostgresDatabase()

    query = """
        SELECT
            d.document_id,
            d.document_key,
            d.status,

            COUNT(DISTINCT dc.chunk_id) AS total_chunks,

            COUNT(
                DISTINCT CASE
                    WHEN dce.provider = %s
                     AND dce.model = %s
                    THEN dc.chunk_id
                END
            ) AS embedded_chunks,

            COUNT(
                DISTINCT CASE
                    WHEN dce.provider = %s
                     AND dce.model = %s
                     AND vector_dims(dce.embedding) = %s
                    THEN dc.chunk_id
                END
            ) AS valid_dimension_chunks

        FROM documents d

        JOIN document_chunks dc
            ON dc.document_id = d.document_id

        LEFT JOIN document_chunk_embeddings dce
            ON dce.chunk_id = dc.chunk_id

        WHERE d.document_key = %s

        GROUP BY
            d.document_id,
            d.document_key,
            d.status;
    """

    params = (
        PROVIDER,
        MODEL,
        PROVIDER,
        MODEL,
        EXPECTED_DIMENSION,
        DOCUMENT_KEY,
    )

    with db.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                params,
            )

            row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            "Document not found: "
            f"{DOCUMENT_KEY}"
        )

    (
        document_id,
        document_key,
        status,
        total_chunks,
        embedded_chunks,
        valid_dimension_chunks,
    ) = row

    total_chunks = int(total_chunks)
    embedded_chunks = int(embedded_chunks)
    valid_dimension_chunks = int(
        valid_dimension_chunks
    )

    missing_embeddings = (
        total_chunks - embedded_chunks
    )

    invalid_dimension_chunks = (
        embedded_chunks
        - valid_dimension_chunks
    )

    print()
    print(f"document_id             = {document_id}")
    print(f"document_key            = {document_key}")
    print(f"document_status         = {status}")
    print()
    print(f"provider                = {PROVIDER}")
    print(f"model                   = {MODEL}")
    print(f"expected_dimension      = {EXPECTED_DIMENSION}")
    print()
    print(f"total_chunks            = {total_chunks}")
    print(f"embedded_chunks         = {embedded_chunks}")
    print(f"missing_embeddings      = {missing_embeddings}")
    print(
        f"valid_dimension_chunks  = "
        f"{valid_dimension_chunks}"
    )
    print(
        f"invalid_dimension_chunks = "
        f"{invalid_dimension_chunks}"
    )

    print("\nRunning assertions...")

    if status != "embedded":
        raise RuntimeError(
            "Document status is not embedded. "
            f"Current status={status}"
        )

    if total_chunks != EXPECTED_CHUNKS:
        raise RuntimeError(
            "Unexpected chunk count: "
            f"expected={EXPECTED_CHUNKS}, "
            f"actual={total_chunks}"
        )

    if embedded_chunks != total_chunks:
        raise RuntimeError(
            "Not every document chunk has an embedding: "
            f"{embedded_chunks}/{total_chunks}"
        )

    if missing_embeddings != 0:
        raise RuntimeError(
            "Document still has missing embeddings: "
            f"{missing_embeddings}"
        )

    if valid_dimension_chunks != total_chunks:
        raise RuntimeError(
            "Some embeddings do not have the expected "
            f"{EXPECTED_DIMENSION} dimensions: "
            f"{valid_dimension_chunks}/{total_chunks}"
        )

    if invalid_dimension_chunks != 0:
        raise RuntimeError(
            "Found embeddings with invalid dimensions: "
            f"{invalid_dimension_chunks}"
        )

    print("[OK] Document status is embedded")
    print(
        f"[OK] All {total_chunks} chunks have embeddings"
    )
    print(
        f"[OK] All embeddings are "
        f"{EXPECTED_DIMENSION}-dimensional"
    )
    print(
        f"[OK] Provider/model = "
        f"{PROVIDER}/{MODEL}"
    )

    print("\n" + "=" * 70)
    print("FULL DOCUMENT EMBEDDING VERIFICATION PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()