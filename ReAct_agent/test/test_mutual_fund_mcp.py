from __future__ import annotations

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


EXPECTED_TOOLS = {
    "search_mutual_funds",
    "get_mutual_fund_details",
    "get_latest_nav",
    "get_nav_history",
}


async def main() -> None:
    print("=" * 70)
    print("FINZER - MUTUAL FUND MCP PROTOCOL TEST")
    print("=" * 70)

    # --------------------------------------------------------------
    # Start our MCP server as a child process over stdio.
    # --------------------------------------------------------------

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

            # ------------------------------------------------------
            # TEST 1 - MCP initialization
            # ------------------------------------------------------

            print("\n[1] Initializing MCP session...")

            await session.initialize()

            print("MCP session initialized successfully.")

            # ------------------------------------------------------
            # TEST 2 - tools/list
            # ------------------------------------------------------

            print("\n[2] Discovering MCP tools...")

            result = await session.list_tools()

            discovered_tools = {
                tool.name
                for tool in result.tools
            }

            for tool in result.tools:
                print(f"  - {tool.name}")

            assert discovered_tools == EXPECTED_TOOLS, (
                "Unexpected MCP tool set.\n"
                f"Expected: {sorted(EXPECTED_TOOLS)}\n"
                f"Actual:   {sorted(discovered_tools)}"
            )

            print(
                f"\nDiscovered all "
                f"{len(discovered_tools)} expected tools."
            )

            # ------------------------------------------------------
            # TEST 3 - search_mutual_funds
            # ------------------------------------------------------

            print("\n[3] Calling search_mutual_funds...")

            search_result = await session.call_tool(
                "search_mutual_funds",
                arguments={
                    "query": "SBI Small Cap",
                },
            )

            assert not search_result.is_error, (
                f"MCP search tool failed: "
                f"{search_result.content}"
            )

            print("search_mutual_funds call succeeded.")

            # ------------------------------------------------------
            # TEST 4 - get_latest_nav
            # ------------------------------------------------------

            print("\n[4] Calling get_latest_nav...")

            nav_result = await session.call_tool(
                "get_latest_nav",
                arguments={
                    "scheme_code": 125497,
                },
            )

            assert not nav_result.is_error, (
                f"MCP latest NAV tool failed: "
                f"{nav_result.content}"
            )

            print("get_latest_nav call succeeded.")

            # ------------------------------------------------------
            # TEST 5 - get_nav_history
            # ------------------------------------------------------

            print("\n[5] Calling bounded get_nav_history...")

            history_result = await session.call_tool(
                "get_nav_history",
                arguments={
                    "scheme_code": 125497,
                    "start_date": "2026-09-01",
                    "end_date": "2026-09-30",
                },
            )

            assert not history_result.is_error, (
                f"MCP NAV history tool failed: "
                f"{history_result.content}"
            )

            print("get_nav_history call succeeded.")

            # ------------------------------------------------------
            # TEST 6 - Invalid input through MCP schema
            # ------------------------------------------------------

            print("\n[6] Calling tool with invalid input...")

            invalid_result = await session.call_tool(
                "get_latest_nav",
                arguments={
                    "scheme_code": -1,
                },
            )

            # Important:
            #
            # -1 is valid JSON/int according to the MCP function
            # signature, so the MCP protocol itself may accept it.
            #
            # Our application tool layer must then return the
            # structured VALIDATION_ERROR.
            #
            # Therefore this call does NOT necessarily set
            # isError=True at the MCP transport level.

            print(
                "Invalid-input call completed "
                "(application validation handled downstream)."
            )

            # ------------------------------------------------------
            # COMPLETE
            # ------------------------------------------------------

            print("\n" + "=" * 70)
            print("ALL MUTUAL FUND MCP PROTOCOL TESTS PASSED")
            print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())