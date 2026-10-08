from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BuiltContext:
    """
    Final context produced for the future RAG generation layer.
    """

    context: str
    sources: list[dict[str, Any]]
    source_count: int
    total_tokens: int


class DocumentContextBuilder:
    """
    Converts ranked document retrieval results into structured,
    citation-friendly LLM context.

    Responsibilities:
        - preserve retrieval ranking
        - remove duplicate chunks
        - enforce a context token budget
        - preserve section/page/table metadata
        - assign stable source numbers

    This class does NOT call an LLM.
    """

    def __init__(
        self,
        *,
        max_context_tokens: int = 4000,
    ):
        if max_context_tokens <= 0:
            raise ValueError(
                "max_context_tokens must be greater than zero."
            )

        self.max_context_tokens = max_context_tokens

    @staticmethod
    def _normalize_content(
        content: str,
    ) -> str:
        """
        Normalize excessive whitespace while preserving line structure
        where possible.
        """

        content = (content or "").strip()

        lines = []

        for line in content.splitlines():
            normalized_line = " ".join(
                line.split()
            )

            if normalized_line:
                lines.append(normalized_line)

        return "\n".join(lines)

    @staticmethod
    def _build_page_label(
        page_start: int | None,
        page_end: int | None,
    ) -> str:
        if page_start is None:
            return "Unknown"

        if (
            page_end is None
            or page_start == page_end
        ):
            return str(page_start)

        return f"{page_start}-{page_end}"

    @staticmethod
    def _estimate_tokens(
        result: dict[str, Any],
    ) -> int:
        """
        Prefer the token count already generated during chunking.

        A small metadata allowance is added because section/page/source
        labels also consume prompt tokens.
        """

        chunk_tokens = result.get("token_count")

        if chunk_tokens is None:
            content = result.get("content") or ""

            # Conservative fallback when token_count is unavailable.
            chunk_tokens = max(
                1,
                len(content) // 4,
            )

        return int(chunk_tokens) + 40

    def build(
        self,
        results: list[dict[str, Any]],
    ) -> BuiltContext:
        """
        Build structured context from ranked retrieval results.
        """

        if not results:
            return BuiltContext(
                context="",
                sources=[],
                source_count=0,
                total_tokens=0,
            )

        selected_sources: list[dict[str, Any]] = []

        seen_chunk_ids: set[int] = set()

        total_tokens = 0

        # ---------------------------------------------------------
        # Select chunks within token budget
        # ---------------------------------------------------------

        for retrieval_rank, result in enumerate(
            results,
            start=1,
        ):
            chunk_id = result.get("chunk_id")

            if chunk_id is None:
                continue

            chunk_id = int(chunk_id)

            # Prevent duplicate retrieval results.
            if chunk_id in seen_chunk_ids:
                continue

            content = self._normalize_content(
                result.get("content") or ""
            )

            if not content:
                continue

            estimated_tokens = self._estimate_tokens(
                result
            )

            # If we already have useful context, do not exceed budget.
            if (
                selected_sources
                and total_tokens + estimated_tokens
                > self.max_context_tokens
            ):
                continue

            # Allow the first source even if a single chunk happens
            # to exceed the configured budget. This prevents returning
            # completely empty context.
            seen_chunk_ids.add(chunk_id)

            source_number = len(
                selected_sources
            ) + 1

            source = {
                "source_number": source_number,
                "retrieval_rank": retrieval_rank,

                "document_id": result.get(
                    "document_id"
                ),

                "document_key": result.get(
                    "document_key"
                ),

                "chunk_id": chunk_id,

                "chunk_index": result.get(
                    "chunk_index"
                ),

                "content_type": result.get(
                    "content_type"
                ),

                "page_start": result.get(
                    "page_start"
                ),

                "page_end": result.get(
                    "page_end"
                ),

                "section": result.get(
                    "section"
                ),

                "subsection": result.get(
                    "subsection"
                ),

                "heading": result.get(
                    "heading"
                ),

                "token_count": result.get(
                    "token_count"
                ),

                "similarity": result.get(
                    "similarity"
                ),

                "content": content,

                "estimated_context_tokens": (
                    estimated_tokens
                ),
            }

            selected_sources.append(source)

            total_tokens += estimated_tokens

        # ---------------------------------------------------------
        # Render structured context
        # ---------------------------------------------------------

        context_blocks = []

        for source in selected_sources:
            page_label = self._build_page_label(
                source["page_start"],
                source["page_end"],
            )

            metadata_lines = [
                f"[Source {source['source_number']}]",
                (
                    f"Retrieval Rank: "
                    f"{source['retrieval_rank']}"
                ),
                (
                    f"Chunk ID: "
                    f"{source['chunk_id']}"
                ),
                (
                    f"Content Type: "
                    f"{source['content_type']}"
                ),
                (
                    f"Pages: "
                    f"{page_label}"
                ),
            ]

            if source["section"]:
                metadata_lines.append(
                    f"Section: {source['section']}"
                )

            if source["subsection"]:
                metadata_lines.append(
                    f"Subsection: {source['subsection']}"
                )

            if source["heading"]:
                metadata_lines.append(
                    f"Heading: {source['heading']}"
                )

            if source["similarity"] is not None:
                metadata_lines.append(
                    "Similarity: "
                    f"{float(source['similarity']):.4f}"
                )

            metadata_lines.append("Content:")

            metadata_lines.append(
                source["content"]
            )

            context_blocks.append(
                "\n".join(metadata_lines)
            )

        context = "\n\n".join(
            context_blocks
        )

        return BuiltContext(
            context=context,
            sources=selected_sources,
            source_count=len(selected_sources),
            total_tokens=total_tokens,
        )