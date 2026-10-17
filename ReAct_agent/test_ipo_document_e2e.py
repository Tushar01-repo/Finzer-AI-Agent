"""Live Phase 3 E2E: PostgreSQL discovery -> IPO identity -> Document RAG.

Run from ReAct_agent: python .\test_ipo_document_e2e.py
Requires ingestion_service database and embedding provider configuration.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from app.agent.entities import IPOEntityLookupService, IPOLookupStatus
from app.tools.document_rag import DocumentRAGTool
from app.tools.document_rag_backend import IngestionDocumentRAGBackend


REPO_ROOT = Path(__file__).resolve().parent.parent
INGESTION_DIR = REPO_ROOT / "ingestion_service"
COMPANY = "Hi-Tech Flow Solutions Limited"
QUESTION = f"Summarize the objects of the offer in {COMPANY} DRHP"


def discover_documents(company_name: str, document_type: str = "DRHP") -> dict:
    """Invoke the existing ingestion discovery bridge; no duplicate SQL."""
    if not INGESTION_DIR.is_dir():
        raise RuntimeError(f"Missing ingestion directory: {INGESTION_DIR}")
    command = [
        sys.executable, "-m", "app.retrieval.document_discovery_bridge",
        "--company-name", company_name,
        "--document-type", document_type,
        "--limit", "100",
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        result = subprocess.run(
            command, cwd=str(INGESTION_DIR), env=env,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=45, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Document discovery timed out") from exc
    for line in reversed(result.stdout.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if result.returncode != 0 or payload.get("status") != "success":
            raise RuntimeError(f"Discovery failed: {payload.get('error')}")
        if not isinstance(payload.get("data"), list):
            raise RuntimeError("Discovery returned malformed document data")
        return payload
    raise RuntimeError(
        "Document discovery did not return JSON. "
        f"Process exit code: {result.returncode}; "
        f"stderr preview: {result.stderr[-500:]}"
    )


def main() -> int:
    print("=" * 68)
    print("FINZER - IPO DOCUMENT DISCOVERY -> DOCUMENT RAG E2E")
    print("=" * 68)

    print("\n[1] Discovering indexed DRHP via PostgreSQL...")
    discovery = discover_documents("Hi-Tech Flow Solutions", "DRHP")
    print("Discovered documents:", discovery.get("count"))
    assert discovery["data"], "No indexed Hi-Tech Flow Solutions DRHP found"

    print("\n[2] Resolving canonical IPO document entity...")
    lookup = IPOEntityLookupService().resolve(QUESTION, discovery)
    print("Lookup status:", lookup.status.value)
    if lookup.status != IPOLookupStatus.RESOLVED or lookup.entity is None:
        raise AssertionError(
            f"Expected a unique indexed DRHP, got {lookup.status.value}: "
            f"{lookup.reason}; candidates={len(lookup.candidates)}"
        )

    entity = lookup.entity
    document_key = entity.canonical_id
    assert document_key, "Resolved entity has no canonical document_key"
    assert entity.metadata["document_type"] == "DRHP"
    print("Company:", entity.metadata["company_name"])
    print("Document key:", document_key)

    print("\n[3] Retrieving evidence using existing Document RAG tool...")
    tool = DocumentRAGTool(backend=IngestionDocumentRAGBackend(timeout_seconds=120))
    response = tool.execute(
        query="What are the objects of the offer and intended use of proceeds?",
        document_key=document_key,
        top_k=5,
        max_context_tokens=4000,
    )
    if response.status != "success" or response.data is None:
        raise AssertionError(f"RAG retrieval failed: {response.error}")

    data = response.data
    assert data.document_key == document_key
    assert data.source_count == len(data.sources)
    assert data.source_count > 0, "RAG returned no sources"
    assert data.context.strip(), "RAG returned empty context"
    for source in data.sources:
        assert source.document_key == document_key, (
            f"Cross-document retrieval detected: {source.document_key}"
        )
        assert source.content.strip(), "Source has empty content"

    print("Source count:", data.source_count)
    print("Context tokens:", data.total_tokens)
    for source in data.sources:
        print(
            f"  rank={source.retrieval_rank} chunk={source.chunk_id} "
            f"page={source.page_start} section={source.section!r} "
            f"similarity={source.similarity}"
        )
    print("\nContext preview:\n", data.context[:1000])
    print("\n" + "=" * 68)
    print("E2E TEST PASSED")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AssertionError, RuntimeError, ValueError) as exc:
        print(f"\nE2E TEST FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
