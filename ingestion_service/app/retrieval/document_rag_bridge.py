from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from app.retrieval.context_builder import DocumentContextBuilder
from app.retrieval.document_retriever import DocumentRetriever


def retrieve_document_context(
    *,
    query: str,
    document_key: str,
    top_k: int = 5,
    max_context_tokens: int = 4000,
) -> dict[str, Any]:
    """
    Retrieve relevant document chunks and build bounded RAG context.

    This bridge intentionally stays inside ingestion_service so it can
    reuse the existing retrieval/indexing implementation without
    duplicating retrieval logic inside ReAct_agent.
    """

    query = query.strip()
    document_key = document_key.strip()

    if not query:
        raise ValueError("query cannot be empty.")

    if not document_key:
        raise ValueError("document_key cannot be empty.")

    if top_k <= 0:
        raise ValueError(
            "top_k must be greater than zero."
        )

    if max_context_tokens <= 0:
        raise ValueError(
            "max_context_tokens must be greater than zero."
        )

    retriever = DocumentRetriever()

    results = retriever.retrieve(
        query=query,
        document_key=document_key,
        top_k=top_k,
    )

    builder = DocumentContextBuilder(
        max_context_tokens=max_context_tokens,
    )

    built = builder.build(results)

    return {
        "context": built.context,
        "sources": built.sources,
        "source_count": built.source_count,
        "total_tokens": built.total_tokens,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Finzer document RAG retrieval bridge."
    )

    parser.add_argument(
        "--query",
        required=True,
    )

    parser.add_argument(
        "--document-key",
        required=True,
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--max-context-tokens",
        type=int,
        default=4000,
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        result = retrieve_document_context(
            query=args.query,
            document_key=args.document_key,
            top_k=args.top_k,
            max_context_tokens=args.max_context_tokens,
        )

        payload = {
            "status": "success",
            "data": result,
            "error": None,
        }

        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            )
        )

    except Exception as exc:
        payload = {
            "status": "error",
            "data": None,
            "error": {
                "type": (
                    "VALIDATION_ERROR"
                    if isinstance(exc, ValueError)
                    else "RETRIEVAL_ERROR"
                ),
                "message": str(exc),
            },
        }

        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            )
        )

        sys.exit(1)


if __name__ == "__main__":
    main()