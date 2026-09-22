from typing import Any

from psycopg.types.json import Json

from app.models.database_schema import ArticleRecord
from app.repositories.database import PostgresDatabase


class ArticleRepository:
    """
    Repository for the articles table.

    Responsibilities:
    - Insert new articles
    - Update existing articles
    - Retrieve articles
    - Maintain processing status
    - Persist LLM analysis results
    """

    def __init__(self, database: PostgresDatabase):
        self.database = database

    def upsert(self, article: ArticleRecord) -> None:
        """
        Insert an article or update the existing article
        identified by article_key.
        """

        query = """
            INSERT INTO articles (
                article_key,
                title,
                url,
                source,
                authors,
                published_at,
                content,
                content_hash,
                summary,
                processing_status
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            ON CONFLICT (article_key)
            DO UPDATE SET
                title = EXCLUDED.title,
                url = EXCLUDED.url,
                source = EXCLUDED.source,
                authors = EXCLUDED.authors,
                published_at = EXCLUDED.published_at,
                content = EXCLUDED.content,
                content_hash = EXCLUDED.content_hash,
                updated_at = NOW()
        """

        params = (
            article.article_key,
            article.title,
            article.url,
            article.source,
            Json(article.authors)
            if article.authors is not None
            else None,
            article.published_at,
            article.content,
            article.content_hash,
            article.summary,
            article.processing_status,
        )

        self.database.execute(query, params)

    def get_by_key(
        self,
        article_key: str,
    ) -> ArticleRecord | None:
        """
        Retrieve an article using its deterministic article_key.
        """

        query = """
            SELECT
                article_key,
                title,
                url,
                source,
                authors,
                published_at,
                content,
                content_hash,
                summary,
                processing_status,
                created_at,
                updated_at
            FROM articles
            WHERE article_key = %s
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (article_key,))
                row = cursor.fetchone()

        if row is None:
            return None

        return self._to_record(row)

    def update_summary(
        self,
        article_key: str,
        summary: str,
    ) -> None:
        """
        Update the generated article summary.
        """

        query = """
            UPDATE articles
            SET
                summary = %s,
                processing_status = 'summarized',
                updated_at = NOW()
            WHERE article_key = %s
        """

        self.database.execute(
            query,
            (summary, article_key),
        )

    def update_processing_status(
        self,
        article_key: str,
        status: str,
    ) -> None:
        """
        Update article processing status.
        """

        query = """
            UPDATE articles
            SET
                processing_status = %s,
                updated_at = NOW()
            WHERE article_key = %s
        """

        self.database.execute(
            query,
            (status, article_key),
        )

    def save_article_analysis(
        self,
        *,
        article_key: str,
        is_valid_article: bool,
        relevance_score: float,
        is_relevant: bool,
        relevance_reason: str,
        summary: str | None,
        key_facts: list[str],
        companies_mentioned: list[str],
        market_impact: str | None,
        llm_analysis: dict[str, Any],
    ) -> None:
        """
        Persist LLM analysis results for an article.

        All analyzed articles are stored, including:
        - valid and relevant articles
        - valid but irrelevant articles
        - invalid extracted content
        """

        if not is_valid_article:
            processing_status = "invalid"

        elif is_relevant:
            processing_status = "analyzed"

        else:
            processing_status = "irrelevant"

        query = """
            UPDATE articles
            SET
                is_valid_article = %s,
                relevance_score = %s,
                is_relevant = %s,
                relevance_reason = %s,
                summary = %s,
                key_facts = %s,
                companies_mentioned = %s,
                market_impact = %s,
                llm_analysis = %s,
                analyzed_at = NOW(),
                processing_status = %s,
                updated_at = NOW()
            WHERE article_key = %s
        """

        params = (
            is_valid_article,
            relevance_score,
            is_relevant,
            relevance_reason,
            summary,
            Json(key_facts),
            Json(companies_mentioned),
            market_impact,
            Json(llm_analysis),
            processing_status,
            article_key,
        )

        self.database.execute(
            query,
            params,
        )


    def get_embedding_input(
        self,
        article_key: str,
    ) -> dict[str, Any] | None:
        """
        Retrieve the canonical fields used to generate an article embedding.

        The raw article content is intentionally excluded. The embedding is
        generated from the LLM-cleaned financial representation of the article.
        """

        query = """
            SELECT
                article_key,
                title,
                summary,
                key_facts,
                market_impact,
                processing_status,
                EXISTS (
                    SELECT 1
                    FROM article_embeddings ae
                    WHERE ae.article_key = articles.article_key
                ) AS has_embedding
            FROM articles
            WHERE article_key = %s
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (article_key,))
                row = cursor.fetchone()

        if row is None:
            return None

        return {
            "article_key": row[0],
            "title": row[1],
            "summary": row[2],
            "key_facts": row[3] or [],
            "market_impact": row[4],
            "processing_status": row[5],
            "has_embedding": bool(row[6]),
        }

    def save_embedding(
        self,
        *,
        article_key: str,
        embedding: list[float],
        expected_dimension: int = 1024,
        embedding_model: str | None = None,
        embedding_provider: str | None = None,
    ) -> None:
        """Persist the current article vector in article_embeddings."""

        if len(embedding) != expected_dimension:
            raise ValueError(
                "Unexpected embedding dimension: "
                f"expected {expected_dimension}, got {len(embedding)}."
            )

        vector_literal = "[" + ",".join(str(float(value)) for value in embedding) + "]"
        model = embedding_model or "unknown"
        provider = embedding_provider or "unknown"

        query = """
            INSERT INTO article_embeddings (
                article_key,
                embedding,
                embedding_model,
                embedding_provider,
                embedding_dimension,
                embedded_at
            )
            VALUES (%s, %s::vector, %s, %s, %s, NOW())
            ON CONFLICT (article_key)
            DO UPDATE SET
                embedding = EXCLUDED.embedding,
                embedding_model = EXCLUDED.embedding_model,
                embedding_provider = EXCLUDED.embedding_provider,
                embedding_dimension = EXCLUDED.embedding_dimension,
                embedded_at = NOW()
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (article_key, vector_literal, model, provider, expected_dimension),
                )
                cursor.execute(
                    """
                    UPDATE articles
                    SET processing_status = 'embedded', updated_at = NOW()
                    WHERE article_key = %s
                    """,
                    (article_key,),
                )

    def get_pending_articles(
        self,
        limit: int = 100,
    ) -> list[ArticleRecord]:
        """
        Retrieve articles waiting for asynchronous processing.
        """

        if limit <= 0:
            raise ValueError(
                "limit must be greater than zero."
            )

        query = """
            SELECT
                article_key,
                title,
                url,
                source,
                authors,
                published_at,
                content,
                content_hash,
                summary,
                processing_status,
                created_at,
                updated_at
            FROM articles
            WHERE processing_status = 'pending'
            ORDER BY created_at
            LIMIT %s
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (limit,),
                )

                rows = cursor.fetchall()

        return [
            self._to_record(row)
            for row in rows
        ]

    @staticmethod
    def _to_record(
        row: tuple[Any, ...],
    ) -> ArticleRecord:
        """
        Convert a database row into an ArticleRecord.
        """

        return ArticleRecord(
            article_key=row[0],
            title=row[1],
            url=row[2],
            source=row[3],
            authors=row[4],
            published_at=row[5],
            content=row[6],
            content_hash=row[7],
            summary=row[8],
            processing_status=row[9],
            created_at=row[10],
            updated_at=row[11],
        )