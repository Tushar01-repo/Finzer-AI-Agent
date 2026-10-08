from app.repositories.database import PostgresDatabase


def main() -> None:
    db = PostgresDatabase()

    with db.connect() as connection:
        with connection.cursor() as cursor:

            print("=" * 80)
            print("ARTICLE EMBEDDING CONFIGURATION")
            print("=" * 80)

            cursor.execute(
                """
                SELECT
                    embedding_provider,
                    embedding_model,
                    embedding_dimension,
                    COUNT(*)
                FROM article_embeddings
                GROUP BY
                    embedding_provider,
                    embedding_model,
                    embedding_dimension
                ORDER BY COUNT(*) DESC
                """
            )

            rows = cursor.fetchall()

            if not rows:
                print("No article embeddings found.")
            else:
                for row in rows:
                    print(
                        f"Provider:  {row[0]}\n"
                        f"Model:     {row[1]}\n"
                        f"Dimension: {row[2]}\n"
                        f"Count:     {row[3]}\n"
                    )

            print()
            print("=" * 80)
            print("LATEST INDEXED ARTICLES")
            print("=" * 80)

            cursor.execute(
                """
                SELECT
                    a.article_key,
                    a.title,
                    a.source,
                    a.published_at,
                    a.processing_status,
                    a.companies_mentioned
                FROM articles a
                INNER JOIN article_embeddings ae
                    ON ae.article_key = a.article_key
                ORDER BY
                    a.published_at DESC NULLS LAST
                LIMIT 10
                """
            )

            rows = cursor.fetchall()

            if not rows:
                print("No indexed articles found.")
                return

            for index, row in enumerate(rows, start=1):
                article_key = row[0]
                title = row[1]
                source = row[2]
                published_at = row[3]
                status = row[4]
                companies = row[5]

                print()
                print(f"[{index}]")
                print(f"Article key: {article_key}")
                print(f"Title:       {title}")
                print(f"Source:      {source}")
                print(f"Published:   {published_at}")
                print(f"Status:      {status}")
                print(f"Companies:   {companies}")


if __name__ == "__main__":
    main()