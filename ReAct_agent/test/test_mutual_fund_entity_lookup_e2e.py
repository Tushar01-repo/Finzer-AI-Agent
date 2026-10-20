
"""Live E2E test: Mutual Fund MCP -> Entity Lookup.

Run from ReAct_agent:
    python .\\test_mutual_fund_entity_lookup_e2e.py

Requires network access to MFAPI.
Does not modify the database or execute write tools.
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.agent.entities import (
    EntityLookupService,
    LookupStatus,
)
from app.agent.entities import MCPLookupAdapter
from app.agent.state import EntityType


SEARCH_QUERY = "SBI Small Cap"


async def main() -> None:
    print("=" * 70)
    print("FINZER - MUTUAL FUND ENTITY LOOKUP E2E TEST")
    print("=" * 70)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "app.mcp_servers.mutual_fund.server",
        ],
    )

    async with stdio_client(server_params) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            print("\n[1] Initializing MCP session...")
            await session.initialize()
            print("MCP session initialized.")

            print("\n[2] Checking search tool...")
            listed = await session.list_tools()
            tool_names = {tool.name for tool in listed.tools}

            assert "search_mutual_funds" in tool_names, (
                "search_mutual_funds is not registered."
            )
            print("search_mutual_funds discovered.")

            print("\n[3] Calling live MFAPI through MCP...")
            result = await session.call_tool(
                "search_mutual_funds",
                arguments={"query": SEARCH_QUERY},
            )

            print("MCP transport error:", result.is_error)

            # Serialize the actual MCP SDK response, preserving
            # content and structuredContent if provided.
            raw_response = result.model_dump(
                mode="json",
                exclude_none=True,
                by_alias=True,
            )

            print("\nMCP response keys:")
            print(sorted(raw_response.keys()))

            if result.is_error:
                raise AssertionError(
                    "MCP protocol reported a tool error: "
                    f"{result.content}"
                )

            print("\n[4] Normalizing MCP response...")
            normalized = (
                MCPLookupAdapter.normalize_search_response(
                    raw_response
                )
            )

            if normalized.get("isError"):
                print(
                    json.dumps(
                        normalized,
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                raise AssertionError(
                    "MCP lookup adapter rejected the response."
                )

            candidates = normalized.get("data", [])

            print("Candidate count:", len(candidates))

            assert candidates, (
                "MFAPI returned no mutual fund candidates."
            )

            print("\nFirst three candidates:")
            print(
                json.dumps(
                    candidates[:3],
                    indent=2,
                    ensure_ascii=False,
                )
            )

            print("\n[5] Resolving canonical entity...")

            # Search terms may be shorter than canonical names.
            # The resolver must not arbitrarily select a
            # Direct/Regular/Growth/IDCW variant.
            lookup = EntityLookupService()

            resolution = lookup.resolve_mutual_fund(
                SEARCH_QUERY,
                normalized,
            )

            print(
                resolution.model_dump_json(
                    indent=2
                )
            )

            assert resolution.status in (
                LookupStatus.RESOLVED,
                LookupStatus.AMBIGUOUS,
            ), (
                "Expected a resolved entity or candidates "
                "requiring clarification."
            )

            if resolution.status == LookupStatus.RESOLVED:
                assert resolution.entity is not None
                assert (
                    resolution.entity.entity_type
                    == EntityType.MUTUAL_FUND
                )
                assert resolution.entity.canonical_id
                assert resolution.entity.canonical_id.isdigit()

                print(
                    "\nCanonical scheme:",
                    resolution.entity.name,
                )
                print(
                    "Scheme code:",
                    resolution.entity.canonical_id,
                )

            else:
                assert resolution.candidates
                assert all(
                    candidate.entity_type
                    == EntityType.MUTUAL_FUND
                    for candidate in resolution.candidates
                )
                assert all(
                    candidate.canonical_id
                    and candidate.canonical_id.isdigit()
                    for candidate in resolution.candidates
                )

                print(
                    "\nMultiple schemes found. "
                    "User clarification is required."
                )

            print("\n[6] Verifying upstream error handling...")

            failed_response = {
                "status": "error",
                "error": {
                    "type": "UPSTREAM_TIMEOUT",
                    "message": "Simulated timeout.",
                    "retryable": True,
                },
            }

            normalized_error = (
                MCPLookupAdapter.normalize_search_response(
                    failed_response
                )
            )

            error_resolution = lookup.resolve_mutual_fund(
                SEARCH_QUERY,
                normalized_error,
            )

            assert (
                error_resolution.status
                == LookupStatus.INVALID_RESPONSE
            )

            print("Structured upstream error rejected.")

    print("\n" + "=" * 70)
    print("E2E TEST PASSED")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())



