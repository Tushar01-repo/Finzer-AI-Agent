from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any, Sequence

from psycopg.types.json import Json

from app.document_ingestion.models import (
    DiscoveredDocument,
    DocumentChunk,
    DownloadedDocument,
)
from app.repositories.database import PostgresDatabase


class DocumentRepository:
    """
    Repository for document ingestion persistence.

    Responsibilities:
    - Insert/update discovered documents
    - Store downloaded PDF metadata
    - Maintain document processing status
    - Persist document chunks transactionally
    - Retrieve chunks for embedding
    - Persist chunk embeddings

    The repository intentionally does not perform:
    - PDF parsing
    - structure detection
    - chunk generation
    - embedding generation
    """

    VALID_STATUSES = {
        "discovered",
        "downloading",
        "downloaded",
        "parsing",
        "parsed",
        "chunked",
        "embedding",
        "embedded",
        "failed",
    }

    EMBEDDING_DIMENSION = 1024

    def __init__(
        self,
        database: PostgresDatabase,
    ):
        self.database = database

    # ============================================================
    # Documents
    # ============================================================

    def upsert_discovered_document(
        self,
        *,
        document_key: str,
        document: DiscoveredDocument,
    ) -> int:
        """
        Insert a newly discovered document or update its source
        metadata if it already exists.

        Existing processing progress is intentionally preserved.

        Returns:
            document_id
        """

        if not document_key:
            raise ValueError(
                "document_key cannot be empty."
            )

        published_at = None

        if document.published_date is not None:
            published_at = datetime.combine(
                document.published_date,
                time.min,
                tzinfo=timezone.utc,
            )

        query = """
            INSERT INTO documents (
                document_key,
                source,
                company_name,
                document_type,
                source_title,
                filing_url,
                pdf_url,
                published_at,
                status,
                metadata
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
                'discovered',
                %s
            )
            ON CONFLICT (document_key)
            DO UPDATE SET
                source = EXCLUDED.source,
                company_name = EXCLUDED.company_name,
                document_type = EXCLUDED.document_type,
                source_title = EXCLUDED.source_title,
                filing_url = EXCLUDED.filing_url,
                pdf_url = EXCLUDED.pdf_url,
                published_at = EXCLUDED.published_at,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING document_id
        """

        params = (
            document_key,
            document.source,
            document.company_name,
            document.document_type,
            document.title,
            document.filing_url,
            document.pdf_url,
            published_at,
            Json(document.metadata),
        )

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    params,
                )

                row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                "Failed to obtain document_id after document upsert."
            )

        return int(row[0])

    def get_by_key(
        self,
        document_key: str,
    ) -> dict[str, Any] | None:
        """
        Retrieve a document using its deterministic document_key.
        """

        query = """
            SELECT
                document_id,
                document_key,
                source,
                company_name,
                document_type,
                source_title,
                filing_url,
                pdf_url,
                file_name,
                file_sha256,
                file_size_bytes,
                published_at,
                status,
                metadata,
                created_at,
                updated_at
            FROM documents
            WHERE document_key = %s
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (document_key,),
                )

                row = cursor.fetchone()

        if row is None:
            return None

        return self._document_row_to_dict(row)

    def get_document_id(
        self,
        document_key: str,
    ) -> int | None:
        """
        Return only the database document_id for a document key.
        """

        query = """
            SELECT document_id
            FROM documents
            WHERE document_key = %s
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (document_key,),
                )

                row = cursor.fetchone()

        if row is None:
            return None

        return int(row[0])

    def update_status(
        self,
        document_key: str,
        status: str,
    ) -> None:
        """
        Update the document lifecycle status.
        """

        if status not in self.VALID_STATUSES:
            raise ValueError(
                f"Invalid document status: {status}. "
                f"Expected one of: "
                f"{sorted(self.VALID_STATUSES)}"
            )

        query = """
            UPDATE documents
            SET
                status = %s,
                updated_at = NOW()
            WHERE document_key = %s
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        status,
                        document_key,
                    ),
                )

                if cursor.rowcount == 0:
                    raise KeyError(
                        "Document not found for "
                        f"document_key={document_key}"
                    )

    def save_downloaded_document(
        self,
        *,
        document_key: str,
        document: DownloadedDocument,
    ) -> None:
        """
        Persist information generated after a PDF has been
        successfully downloaded and validated.
        """

        query = """
            UPDATE documents
            SET
                file_name = %s,
                file_sha256 = %s,
                file_size_bytes = %s,
                status = 'downloaded',
                updated_at = NOW()
            WHERE document_key = %s
        """

        params = (
            document.file_name,
            document.file_sha256,
            document.file_size_bytes,
            document_key,
        )

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    params,
                )

                if cursor.rowcount == 0:
                    raise KeyError(
                        "Document not found for "
                        f"document_key={document_key}"
                    )

    # ============================================================
    # Chunks
    # ============================================================

    def replace_chunks(
        self,
        *,
        document_key: str,
        chunks: Sequence[DocumentChunk],
    ) -> int:
        """
        Atomically replace all chunks belonging to a document.

        Transaction:

            DELETE existing chunks
                    ↓
            INSERT new chunks
                    ↓
            status = chunked
                    ↓
            COMMIT

        If any chunk insertion fails, the entire transaction is
        rolled back automatically.

        Because document_chunk_embeddings references chunks using
        ON DELETE CASCADE, replacing chunks also removes embeddings
        belonging to the previous chunk set.

        Returns:
            Number of chunks inserted.
        """

        self._validate_chunks(chunks)

        with self.database.connect() as connection:
            with connection.cursor() as cursor:

                # --------------------------------------------------
                # Lock document row and resolve document_id
                # --------------------------------------------------

                cursor.execute(
                    """
                    SELECT document_id
                    FROM documents
                    WHERE document_key = %s
                    FOR UPDATE
                    """,
                    (document_key,),
                )

                row = cursor.fetchone()

                if row is None:
                    raise KeyError(
                        "Document not found for "
                        f"document_key={document_key}"
                    )

                document_id = int(row[0])

                # --------------------------------------------------
                # Delete previous chunks
                #
                # Previous embeddings are automatically deleted by
                # ON DELETE CASCADE.
                # --------------------------------------------------

                cursor.execute(
                    """
                    DELETE FROM document_chunks
                    WHERE document_id = %s
                    """,
                    (document_id,),
                )

                # --------------------------------------------------
                # Insert new chunks
                # --------------------------------------------------

                insert_query = """
                    INSERT INTO document_chunks (
                        document_id,
                        chunk_index,
                        content_type,
                        content,
                        page_start,
                        page_end,
                        section,
                        subsection,
                        heading,
                        token_count,
                        metadata
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
                        %s,
                        %s
                    )
                """

                for chunk in chunks:
                    content_type = (
                        chunk.content_type.value
                        if hasattr(
                            chunk.content_type,
                            "value",
                        )
                        else str(chunk.content_type)
                    )

                    cursor.execute(
                        insert_query,
                        (
                            document_id,
                            chunk.chunk_index,
                            content_type,
                            chunk.content,
                            chunk.page_start,
                            chunk.page_end,
                            chunk.section,
                            chunk.subsection,
                            chunk.heading,
                            chunk.token_count,
                            Json(chunk.metadata),
                        ),
                    )

                # --------------------------------------------------
                # Mark document chunked
                # --------------------------------------------------

                cursor.execute(
                    """
                    UPDATE documents
                    SET
                        status = 'chunked',
                        updated_at = NOW()
                    WHERE document_id = %s
                    """,
                    (document_id,),
                )

        return len(chunks)

    def get_chunk(
        self,
        chunk_id: int,
    ) -> dict[str, Any] | None:
        """
        Retrieve one document chunk.
        """

        query = """
            SELECT
                dc.chunk_id,
                dc.document_id,
                d.document_key,
                dc.chunk_index,
                dc.content_type,
                dc.content,
                dc.page_start,
                dc.page_end,
                dc.section,
                dc.subsection,
                dc.heading,
                dc.token_count,
                dc.metadata,
                dc.created_at
            FROM document_chunks dc
            JOIN documents d
                ON d.document_id = dc.document_id
            WHERE dc.chunk_id = %s
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (chunk_id,),
                )

                row = cursor.fetchone()

        if row is None:
            return None

        return self._chunk_row_to_dict(row)

    def get_chunks_for_document(
        self,
        document_key: str,
    ) -> list[dict[str, Any]]:
        """
        Retrieve all chunks belonging to a document in their
        original chunk order.
        """

        query = """
            SELECT
                dc.chunk_id,
                dc.document_id,
                d.document_key,
                dc.chunk_index,
                dc.content_type,
                dc.content,
                dc.page_start,
                dc.page_end,
                dc.section,
                dc.subsection,
                dc.heading,
                dc.token_count,
                dc.metadata,
                dc.created_at
            FROM document_chunks dc
            JOIN documents d
                ON d.document_id = dc.document_id
            WHERE d.document_key = %s
            ORDER BY dc.chunk_index
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (document_key,),
                )

                rows = cursor.fetchall()

        return [
            self._chunk_row_to_dict(row)
            for row in rows
        ]

    # ============================================================
    # Embedding input
    # ============================================================

    def get_embedding_input(
        self,
        chunk_id: int,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Retrieve the canonical text and metadata needed to embed
        one document chunk.

        If provider and model are supplied, has_embedding indicates
        whether that exact provider/model combination already exists.

        If provider/model are omitted, has_embedding indicates
        whether any embedding exists for the chunk.
        """

        if (provider is None) != (model is None):
            raise ValueError(
                "provider and model must either both be supplied "
                "or both be omitted."
            )

        if provider is not None and model is not None:
            query = """
                SELECT
                    dc.chunk_id,
                    dc.document_id,
                    d.document_key,
                    d.company_name,
                    d.document_type,
                    d.source_title,
                    dc.chunk_index,
                    dc.content_type,
                    dc.content,
                    dc.page_start,
                    dc.page_end,
                    dc.section,
                    dc.subsection,
                    dc.heading,
                    dc.token_count,
                    EXISTS (
                        SELECT 1
                        FROM document_chunk_embeddings dce
                        WHERE
                            dce.chunk_id = dc.chunk_id
                            AND dce.provider = %s
                            AND dce.model = %s
                    ) AS has_embedding
                FROM document_chunks dc
                JOIN documents d
                    ON d.document_id = dc.document_id
                WHERE dc.chunk_id = %s
            """

            params = (
                provider,
                model,
                chunk_id,
            )

        else:
            query = """
                SELECT
                    dc.chunk_id,
                    dc.document_id,
                    d.document_key,
                    d.company_name,
                    d.document_type,
                    d.source_title,
                    dc.chunk_index,
                    dc.content_type,
                    dc.content,
                    dc.page_start,
                    dc.page_end,
                    dc.section,
                    dc.subsection,
                    dc.heading,
                    dc.token_count,
                    EXISTS (
                        SELECT 1
                        FROM document_chunk_embeddings dce
                        WHERE dce.chunk_id = dc.chunk_id
                    ) AS has_embedding
                FROM document_chunks dc
                JOIN documents d
                    ON d.document_id = dc.document_id
                WHERE dc.chunk_id = %s
            """

            params = (chunk_id,)

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    params,
                )

                row = cursor.fetchone()

        if row is None:
            return None

        return {
            "chunk_id": row[0],
            "document_id": row[1],
            "document_key": row[2],
            "company_name": row[3],
            "document_type": row[4],
            "source_title": row[5],
            "chunk_index": row[6],
            "content_type": row[7],
            "content": row[8],
            "page_start": row[9],
            "page_end": row[10],
            "section": row[11],
            "subsection": row[12],
            "heading": row[13],
            "token_count": row[14],
            "has_embedding": bool(row[15]),
        }

    def get_chunks_pending_embedding(
        self,
        *,
        provider: str,
        model: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Return chunks that do not yet have an embedding for the
        requested provider/model pair.

        This will later be useful for the document embedding worker.
        """

        if not provider:
            raise ValueError(
                "provider cannot be empty."
            )

        if not model:
            raise ValueError(
                "model cannot be empty."
            )

        if limit <= 0:
            raise ValueError(
                "limit must be greater than zero."
            )

        query = """
            SELECT
                dc.chunk_id,
                dc.document_id,
                d.document_key,
                d.company_name,
                d.document_type,
                d.source_title,
                dc.chunk_index,
                dc.content_type,
                dc.content,
                dc.page_start,
                dc.page_end,
                dc.section,
                dc.subsection,
                dc.heading,
                dc.token_count
            FROM document_chunks dc
            JOIN documents d
                ON d.document_id = dc.document_id
            WHERE
                d.status IN (
                    'chunked',
                    'embedding'
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM document_chunk_embeddings dce
                    WHERE
                        dce.chunk_id = dc.chunk_id
                        AND dce.provider = %s
                        AND dce.model = %s
                )
            ORDER BY
                d.created_at,
                dc.chunk_index
            LIMIT %s
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        provider,
                        model,
                        limit,
                    ),
                )

                rows = cursor.fetchall()

        return [
            {
                "chunk_id": row[0],
                "document_id": row[1],
                "document_key": row[2],
                "company_name": row[3],
                "document_type": row[4],
                "source_title": row[5],
                "chunk_index": row[6],
                "content_type": row[7],
                "content": row[8],
                "page_start": row[9],
                "page_end": row[10],
                "section": row[11],
                "subsection": row[12],
                "heading": row[13],
                "token_count": row[14],
                "has_embedding": False,
            }
            for row in rows
        ]

    # ============================================================
    # Embeddings
    # ============================================================

    def has_embedding(
        self,
        *,
        chunk_id: int,
        provider: str,
        model: str,
    ) -> bool:
        """
        Check whether a chunk already has an embedding for the
        requested provider/model combination.
        """

        query = """
            SELECT EXISTS (
                SELECT 1
                FROM document_chunk_embeddings
                WHERE
                    chunk_id = %s
                    AND provider = %s
                    AND model = %s
            )
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        chunk_id,
                        provider,
                        model,
                    ),
                )

                row = cursor.fetchone()

        return bool(row[0]) if row else False

    def save_embedding(
        self,
        *,
        chunk_id: int,
        embedding: Sequence[float],
        provider: str,
        model: str,
        expected_dimension: int = EMBEDDING_DIMENSION,
    ) -> None:
        """
        Persist or replace an embedding for one document chunk.

        Embeddings are unique by:
            chunk_id + provider + model
        """

        if not provider:
            raise ValueError(
                "provider cannot be empty."
            )

        if not model:
            raise ValueError(
                "model cannot be empty."
            )

        if expected_dimension != self.EMBEDDING_DIMENSION:
            raise ValueError(
                "The current database schema requires "
                f"{self.EMBEDDING_DIMENSION}-dimensional vectors."
            )

        if len(embedding) != expected_dimension:
            raise ValueError(
                "Unexpected embedding dimension: "
                f"expected {expected_dimension}, "
                f"got {len(embedding)}."
            )

        vector_literal = (
            "["
            + ",".join(
                str(float(value))
                for value in embedding
            )
            + "]"
        )

        query = """
            INSERT INTO document_chunk_embeddings (
                chunk_id,
                provider,
                model,
                dimension,
                embedding
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s::vector
            )
            ON CONFLICT (
                chunk_id,
                provider,
                model
            )
            DO UPDATE SET
                dimension = EXCLUDED.dimension,
                embedding = EXCLUDED.embedding,
                created_at = NOW()
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:

                # Verify chunk exists before attempting insert.
                cursor.execute(
                    """
                    SELECT document_id
                    FROM document_chunks
                    WHERE chunk_id = %s
                    """,
                    (chunk_id,),
                )

                row = cursor.fetchone()

                if row is None:
                    raise KeyError(
                        "Document chunk not found for "
                        f"chunk_id={chunk_id}"
                    )

                cursor.execute(
                    query,
                    (
                        chunk_id,
                        provider,
                        model,
                        expected_dimension,
                        vector_literal,
                    ),
                )

    def mark_document_embedding(
        self,
        document_key: str,
    ) -> None:
        """
        Mark a document as currently being embedded.
        """

        self.update_status(
            document_key,
            "embedding",
        )

    def mark_document_embedded_if_complete(
        self,
        *,
        document_key: str,
        provider: str,
        model: str,
    ) -> bool:
        """
        Mark a document as embedded only when every chunk has an
        embedding for the requested provider/model combination.

        Returns:
            True  -> all chunks embedded and status updated
            False -> one or more chunks still missing embeddings
        """

        with self.database.connect() as connection:
            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT document_id
                    FROM documents
                    WHERE document_key = %s
                    FOR UPDATE
                    """,
                    (document_key,),
                )

                row = cursor.fetchone()

                if row is None:
                    raise KeyError(
                        "Document not found for "
                        f"document_key={document_key}"
                    )

                document_id = int(row[0])

                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total_chunks,
                        COUNT(dce.embedding_id)
                            AS embedded_chunks
                    FROM document_chunks dc
                    LEFT JOIN document_chunk_embeddings dce
                        ON
                            dce.chunk_id = dc.chunk_id
                            AND dce.provider = %s
                            AND dce.model = %s
                    WHERE dc.document_id = %s
                    """,
                    (
                        provider,
                        model,
                        document_id,
                    ),
                )

                counts = cursor.fetchone()

                total_chunks = int(counts[0])
                embedded_chunks = int(counts[1])

                if total_chunks == 0:
                    return False

                if embedded_chunks != total_chunks:
                    return False

                cursor.execute(
                    """
                    UPDATE documents
                    SET
                        status = 'embedded',
                        updated_at = NOW()
                    WHERE document_id = %s
                    """,
                    (document_id,),
                )

        return True

    # ============================================================
    # Validation
    # ============================================================

    @staticmethod
    def _validate_chunks(
        chunks: Sequence[DocumentChunk],
    ) -> None:
        """
        Validate chunks before opening the replacement transaction.
        """

        seen_indexes: set[int] = set()

        for chunk in chunks:

            if chunk.chunk_index < 0:
                raise ValueError(
                    "chunk_index cannot be negative."
                )

            if chunk.chunk_index in seen_indexes:
                raise ValueError(
                    "Duplicate chunk_index found: "
                    f"{chunk.chunk_index}"
                )

            seen_indexes.add(
                chunk.chunk_index
            )

            if not chunk.content.strip():
                raise ValueError(
                    "Chunk content cannot be empty. "
                    f"chunk_index={chunk.chunk_index}"
                )

            if chunk.page_start <= 0:
                raise ValueError(
                    "page_start must be greater than zero. "
                    f"chunk_index={chunk.chunk_index}"
                )

            if chunk.page_end < chunk.page_start:
                raise ValueError(
                    "page_end cannot be smaller than "
                    "page_start. "
                    f"chunk_index={chunk.chunk_index}"
                )

            if chunk.token_count is None:
                raise ValueError(
                    "token_count cannot be None when "
                    "persisting a chunk. "
                    f"chunk_index={chunk.chunk_index}"
                )

            if chunk.token_count < 0:
                raise ValueError(
                    "token_count cannot be negative. "
                    f"chunk_index={chunk.chunk_index}"
                )

    # ============================================================
    # Row conversion
    # ============================================================

    @staticmethod
    def _document_row_to_dict(
        row: tuple[Any, ...],
    ) -> dict[str, Any]:
        return {
            "document_id": row[0],
            "document_key": row[1],
            "source": row[2],
            "company_name": row[3],
            "document_type": row[4],
            "source_title": row[5],
            "filing_url": row[6],
            "pdf_url": row[7],
            "file_name": row[8],
            "file_sha256": row[9],
            "file_size_bytes": row[10],
            "published_at": row[11],
            "status": row[12],
            "metadata": row[13] or {},
            "created_at": row[14],
            "updated_at": row[15],
        }

    @staticmethod
    def _chunk_row_to_dict(
        row: tuple[Any, ...],
    ) -> dict[str, Any]:
        return {
            "chunk_id": row[0],
            "document_id": row[1],
            "document_key": row[2],
            "chunk_index": row[3],
            "content_type": row[4],
            "content": row[5],
            "page_start": row[6],
            "page_end": row[7],
            "section": row[8],
            "subsection": row[9],
            "heading": row[10],
            "token_count": row[11],
            "metadata": row[12] or {},
            "created_at": row[13],
        }