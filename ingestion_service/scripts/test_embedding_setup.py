import sys
import traceback

import psycopg

from app.config.settings import settings
from app.clients.embedding_router import EmbeddingRouter


def print_section(number: int, title: str) -> None:
    print()
    print(f"[{number}] {title}")


def main():
    print("=" * 70)
    print("Finzer Embedding Setup Test")
    print("=" * 70)

    conn = None

    try:
        # ============================================================
        # 1. PostgreSQL connection
        # ============================================================
        print_section(1, "Checking PostgreSQL...")

        conn = psycopg.connect(settings.DATABASE_URL)

        database, user = conn.execute(
            """
            SELECT current_database(), current_user
            """
        ).fetchone()

        print(f"Database: {database}")
        print(f"User:     {user}")
        print("PostgreSQL: OK")

        # ============================================================
        # 2. pgvector extension
        # ============================================================
        print_section(2, "Checking pgvector...")

        result = conn.execute(
            """
            SELECT extversion
            FROM pg_extension
            WHERE extname = 'vector'
            """
        ).fetchone()

        if result is None:
            raise RuntimeError(
                "pgvector extension is not installed in the database."
            )

        pgvector_version = result[0]

        print(f"pgvector version: {pgvector_version}")
        print("pgvector: OK")

        # ============================================================
        # 3. article_embeddings table
        # ============================================================
        print_section(3, "Checking article_embeddings table...")

        table_exists = conn.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'article_embeddings'
            )
            """
        ).fetchone()[0]

        if not table_exists:
            raise RuntimeError(
                "article_embeddings table does not exist."
            )

        print("article_embeddings: EXISTS")

        # ============================================================
        # 4. Embedding vector dimension
        # ============================================================
        print_section(4, "Checking embedding column dimension...")

        result = conn.execute(
            """
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class t
              ON a.attrelid = t.oid
            JOIN pg_namespace n
              ON t.relnamespace = n.oid
            WHERE n.nspname = 'public'
              AND t.relname = 'article_embeddings'
              AND a.attname = 'embedding'
              AND NOT a.attisdropped
            """
        ).fetchone()

        if result is None:
            raise RuntimeError(
                "embedding column was not found in "
                "public.article_embeddings."
            )

        vector_type = result[0]

        print(f"Database vector type: {vector_type}")

        expected_vector_type = "vector(1024)"

        if vector_type != expected_vector_type:
            raise RuntimeError(
                f"Embedding dimension mismatch. "
                f"Expected {expected_vector_type}, "
                f"but database contains {vector_type}."
            )

        print("Vector dimension: OK")

        # ============================================================
        # 5. Existing embeddings
        # ============================================================
        print_section(5, "Checking existing embeddings...")

        embedding_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM public.article_embeddings
            """
        ).fetchone()[0]

        print(f"Existing embedding rows: {embedding_count}")

        # Database checks are finished.
        conn.close()
        conn = None

        # ============================================================
        # 6. Initialize embedding router
        # ============================================================
        print_section(6, "Testing embedding provider routing...")

        router = EmbeddingRouter()

        print("Embedding router initialized successfully.")

        # ============================================================
        # 7. Generate real embedding
        # ============================================================
        print_section(7, "Generating real test embedding...")

        test_text = (
            "Infosys reported strong quarterly revenue growth "
            "and improved its financial outlook."
        )

        print(f"Test text: {test_text}")

        embedding = router.embed(test_text)

        if embedding is None:
            raise RuntimeError(
                "Embedding provider returned None."
            )

        if not isinstance(embedding, (list, tuple)):
            raise RuntimeError(
                "Embedding provider did not return a list or tuple. "
                f"Received: {type(embedding).__name__}"
            )

        actual_dimension = len(embedding)

        print("Embedding generated: YES")
        print(f"Embedding dimension: {actual_dimension}")
        print(f"First 5 values: {embedding[:5]}")

        expected_dimension = 1024

        if actual_dimension != expected_dimension:
            raise RuntimeError(
                f"Expected {expected_dimension} dimensions, "
                f"but received {actual_dimension}."
            )

        print("Embedding dimension: OK")

        # ============================================================
        # 8. Basic embedding sanity check
        # ============================================================
        print_section(8, "Checking embedding values...")

        if not all(
            isinstance(value, (int, float))
            for value in embedding
        ):
            raise RuntimeError(
                "Embedding contains non-numeric values."
            )

        print("Embedding values are numeric: OK")

        # ============================================================
        # SUCCESS
        # ============================================================
        print()
        print("=" * 70)
        print("ALL EMBEDDING CHECKS PASSED")
        print("=" * 70)

        print()
        print("Finzer embedding infrastructure is ready.")
        print(f"Vector dimension: {actual_dimension}")
        print(f"Existing DB embeddings: {embedding_count}")

        print()
        print("Expected routing with current configuration:")
        print("Bedrock Titan -> unavailable")
        print("OpenAI        -> selected")
        print("Model         -> text-embedding-3-small")
        print("Dimension     -> 1024")

    except Exception as exc:
        print()
        print("=" * 70)
        print("EMBEDDING SETUP TEST FAILED")
        print("=" * 70)

        print()
        print(f"Error type: {type(exc).__name__}")
        print(f"Error: {exc}")

        print()
        print("Traceback:")
        traceback.print_exc()

        sys.exit(1)

    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()