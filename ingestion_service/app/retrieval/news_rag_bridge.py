from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from app.retrieval.news_retriever import NewsRetriever


def _parse_datetime(
    value: str | None,
) -> datetime | None:
    if value is None:
        return None

    value = value.strip()

    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError(
            f"Invalid ISO datetime: {value}"
        ) from exc


def retrieve_news(
    *,
    query: str,
    top_k: int = 5,
    company: str | None = None,
    published_after: str | None = None,
    published_before: str | None = None,
) -> dict[str, Any]:
    query = query.strip()

    if not query:
        raise ValueError("query cannot be empty.")

    if top_k <= 0:
        raise ValueError(
            "top_k must be greater than zero."
        )

    if top_k > 50:
        raise ValueError(
            "top_k cannot be greater than 50."
        )

    normalized_company = None

    if company is not None:
        normalized_company = company.strip()

        if not normalized_company:
            raise ValueError(
                "company cannot be empty when provided."
            )

    after = _parse_datetime(
        published_after
    )

    before = _parse_datetime(
        published_before
    )

    if (
        after is not None
        and before is not None
        and after > before
    ):
        raise ValueError(
            "published_after cannot be later "
            "than published_before."
        )

    retriever = NewsRetriever()

    results = retriever.retrieve(
        query=query,
        top_k=top_k,
        company=normalized_company,
        published_after=after,
        published_before=before,
    )

    return {
        "query": query,
        "company": normalized_company,
        "published_after": after,
        "published_before": before,
        "source_count": len(results),
        "sources": results,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Finzer financial news RAG retrieval bridge."
        )
    )

    parser.add_argument(
        "--query",
        required=True,
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--company",
        default=None,
    )

    parser.add_argument(
        "--published-after",
        default=None,
    )

    parser.add_argument(
        "--published-before",
        default=None,
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        result = retrieve_news(
            query=args.query,
            top_k=args.top_k,
            company=args.company,
            published_after=args.published_after,
            published_before=args.published_before,
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