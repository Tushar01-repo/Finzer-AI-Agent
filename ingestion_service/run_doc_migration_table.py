from pathlib import Path

import psycopg

from app.config.settings import settings


MIGRATION_FILE = Path(
    "app/db/migrations/002_create_document_tables.sql"
)


def main():
    print("=" * 70)
    print("Finzer Document Schema Migration")
    print("=" * 70)

    if not MIGRATION_FILE.exists():
        raise FileNotFoundError(
            f"Migration file not found: {MIGRATION_FILE}"
        )

    sql = MIGRATION_FILE.read_text(
        encoding="utf-8"
    )

    print(f"\nMigration file: {MIGRATION_FILE}")

    try:
        with psycopg.connect(
            settings.DATABASE_URL
        ) as conn:

            with conn.cursor() as cursor:

                # ------------------------------------------------------
                # Confirm target database
                # ------------------------------------------------------
                cursor.execute(
                    "SELECT current_database()"
                )

                database_name = cursor.fetchone()[0]

                print(
                    f"Target database: {database_name}"
                )

                if database_name != "finzer":
                    raise RuntimeError(
                        "Refusing to run migration because "
                        f"current database is '{database_name}', "
                        "not 'finzer'."
                    )

                # ------------------------------------------------------
                # Execute migration
                # ------------------------------------------------------
                print("\nExecuting migration...")

                cursor.execute(sql)

            # Explicit commit.
            conn.commit()

        print("\nMigration executed successfully.")

        # --------------------------------------------------------------
        # Verify using a new connection
        # --------------------------------------------------------------
        verify_schema()

    except Exception as exc:
        print("\n" + "=" * 70)
        print("Migration FAILED")
        print("=" * 70)

        print(
            f"{type(exc).__name__}: {exc}"
        )

        raise


def verify_schema():
    expected_tables = {
        "documents",
        "document_chunks",
        "document_chunk_embeddings",
    }

    print("\nVerifying document schema...")

    with psycopg.connect(
        settings.DATABASE_URL
    ) as conn:

        with conn.cursor() as cursor:

            # ----------------------------------------------------------
            # Verify tables
            # ----------------------------------------------------------
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
                """
            )

            all_tables = {
                row[0]
                for row in cursor.fetchall()
            }

            print("\nDocument tables:")

            for table in sorted(expected_tables):

                exists = table in all_tables

                marker = "OK" if exists else "MISSING"

                print(
                    f"  [{marker}] {table}"
                )

            missing = (
                expected_tables - all_tables
            )

            if missing:
                raise RuntimeError(
                    "Missing expected tables: "
                    + ", ".join(
                        sorted(missing)
                    )
                )

            # ----------------------------------------------------------
            # Verify vector column
            # ----------------------------------------------------------
            cursor.execute(
                """
                SELECT
                    column_name,
                    udt_name
                FROM information_schema.columns
                WHERE
                    table_schema = 'public'
                    AND table_name =
                        'document_chunk_embeddings'
                    AND column_name = 'embedding'
                """
            )

            vector_column = cursor.fetchone()

            print("\nEmbedding column:")

            if vector_column is None:
                raise RuntimeError(
                    "Embedding column was not created."
                )

            print(
                f"  {vector_column[0]} -> "
                f"{vector_column[1]}"
            )

            # ----------------------------------------------------------
            # Verify VECTOR(1024)
            # ----------------------------------------------------------
            cursor.execute(
                """
                SELECT format_type(
                    a.atttypid,
                    a.atttypmod
                )
                FROM pg_attribute a
                JOIN pg_class c
                    ON c.oid = a.attrelid
                JOIN pg_namespace n
                    ON n.oid = c.relnamespace
                WHERE
                    n.nspname = 'public'
                    AND c.relname =
                        'document_chunk_embeddings'
                    AND a.attname = 'embedding'
                    AND a.attnum > 0
                    AND NOT a.attisdropped
                """
            )

            vector_type = cursor.fetchone()

            if vector_type is None:
                raise RuntimeError(
                    "Could not determine embedding "
                    "column type."
                )

            print(
                f"  type -> {vector_type[0]}"
            )

            if vector_type[0] != "vector(1024)":
                raise RuntimeError(
                    "Unexpected embedding type: "
                    f"{vector_type[0]}"
                )

            # ----------------------------------------------------------
            # Existing article tables should still exist
            # ----------------------------------------------------------
            print("\nExisting news tables:")

            for table in [
                "articles",
                "article_embeddings",
                "article_feeds",
                "feeds",
            ]:
                exists = table in all_tables

                marker = (
                    "OK"
                    if exists
                    else "MISSING"
                )

                print(
                    f"  [{marker}] {table}"
                )

    print("\n" + "=" * 70)
    print("Document schema verification PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()