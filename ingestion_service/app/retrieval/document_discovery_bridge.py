
"""Document discovery bridge for Finzer ReAct Agent.

Phase 3.5 — Read-only IPO document discovery.

Runs inside ingestion_service and reuses:
- PostgresDatabase
- DocumentRepository.search_documents()

CLI output is a single JSON payload on stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from app.repositories.database import PostgresDatabase
from app.repositories.document_repository import DocumentRepository


def discover_documents(
    *,
    company_name: str | None = None,
    document_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Discover indexed documents using existing repository logic.

    Only documents eligible for retrieval are returned by
    DocumentRepository.search_documents().
    """

    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError("limit must be an integer.")

    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500.")

    if company_name is not None:
        company_name = company_name.strip() or None

    if document_type is not None:
        document_type = document_type.strip().upper() or None

    database = PostgresDatabase()
    repository = DocumentRepository(database)

    return repository.search_documents(
        company_name=company_name,
        document_type=document_type,
        limit=limit,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Finzer read-only document discovery bridge."
    )

    parser.add_argument(
        "--company-name",
        default=None,
        help="Optional company name filter.",
    )

    parser.add_argument(
        "--document-type",
        default=None,
        help="Optional document type filter, e.g. DRHP or RHP.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of documents to return (1-500).",
    )

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        documents = discover_documents(
            company_name=args.company_name,
            document_type=args.document_type,
            limit=args.limit,
        )

        payload = {
            "status": "success",
            "data": documents,
            "count": len(documents),
            "error": None,
        }

        print(json.dumps(payload, ensure_ascii=False))
        return 0

    except Exception as exc:
        payload = {
            "status": "error",
            "data": [],
            "count": 0,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }

        print(json.dumps(payload, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
