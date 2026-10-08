import psycopg

from app.config.settings import settings


def main():
    print("=" * 70)
    print("Finzer PostgreSQL Connection Check")
    print("=" * 70)

    try:
        with psycopg.connect(settings.DATABASE_URL) as conn:
            with conn.cursor() as cursor:

                # ------------------------------------------------------
                # PostgreSQL version
                # ------------------------------------------------------
                cursor.execute("SELECT version()")
                postgres_version = cursor.fetchone()[0]

                print("\nPostgreSQL:")
                print(postgres_version)

                # ------------------------------------------------------
                # Current database
                # ------------------------------------------------------
                cursor.execute("SELECT current_database()")
                database_name = cursor.fetchone()[0]

                print("\nDatabase:")
                print(database_name)

                # ------------------------------------------------------
                # Current user
                # ------------------------------------------------------
                cursor.execute("SELECT current_user")
                database_user = cursor.fetchone()[0]

                print("\nUser:")
                print(database_user)

                # ------------------------------------------------------
                # pgvector extension
                # ------------------------------------------------------
                cursor.execute(
                    """
                    SELECT extversion
                    FROM pg_extension
                    WHERE extname = %s
                    """,
                    ("vector",),
                )

                vector_result = cursor.fetchone()

                print("\npgvector:")

                if vector_result:
                    print(vector_result[0])
                else:
                    print("NOT INSTALLED")

                # ------------------------------------------------------
                # Existing public tables
                # ------------------------------------------------------
                cursor.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                    """
                )

                tables = [
                    row[0]
                    for row in cursor.fetchall()
                ]

                print("\nExisting public tables:")

                if tables:
                    for table in tables:
                        print(f"  - {table}")
                else:
                    print("  No tables found.")

        print("\n" + "=" * 70)
        print("Connection check completed successfully.")
        print("=" * 70)

    except Exception as exc:
        print("\n" + "=" * 70)
        print("Connection check FAILED")
        print("=" * 70)
        print(f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()