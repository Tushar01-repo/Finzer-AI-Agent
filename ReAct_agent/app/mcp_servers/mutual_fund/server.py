from __future__ import annotations

from mcp.server import MCPServer

from app.mcp_servers.mutual_fund.tools import MutualFundTools


# ----------------------------------------------------------------------
# MCP Server
# ----------------------------------------------------------------------

mcp = MCPServer(
    "finzer-mutual-fund-mcp"
)

tools = MutualFundTools()


# ----------------------------------------------------------------------
# MCP Tools
# ----------------------------------------------------------------------

@mcp.tool()
def search_mutual_funds(
    query: str,
) -> dict:
    """
    Search Indian mutual fund schemes by fund name or search text.

    Use this tool when the user provides a mutual fund name but the
    scheme code is not yet known.

    Example:
        query="SBI Small Cap"

    Returns matching mutual fund schemes including their scheme codes.
    """

    response = tools.search_mutual_funds(
        query=query,
    )

    return response.model_dump(
        mode="json",
        exclude_none=True,
    )


@mcp.tool()
def get_mutual_fund_details(
    scheme_code: int,
) -> dict:
    """
    Get metadata for an Indian mutual fund scheme.

    Use this tool when the MFAPI scheme code is already known.

    Returns information such as:
    - scheme name
    - fund house
    - scheme type
    - scheme category
    """

    response = tools.get_mutual_fund_details(
        scheme_code=scheme_code,
    )

    return response.model_dump(
        mode="json",
        exclude_none=True,
    )


@mcp.tool()
def get_latest_nav(
    scheme_code: int,
) -> dict:
    """
    Get the latest available NAV for an Indian mutual fund scheme.

    The scheme_code must identify a specific mutual fund scheme.

    Returns:
    - scheme code
    - scheme name
    - latest NAV
    - NAV date
    """

    response = tools.get_latest_nav(
        scheme_code=scheme_code,
    )

    return response.model_dump(
        mode="json",
        exclude_none=True,
    )


@mcp.tool()
def get_nav_history(
    scheme_code: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """
    Get historical NAV observations for an Indian mutual fund scheme.

    Dates may be supplied as:
    - YYYY-MM-DD
    - DD-MM-YYYY

    Prefer a bounded date range when historical NAV data is required.

    Args:
        scheme_code:
            MFAPI mutual fund scheme code.

        start_date:
            Optional beginning of the requested NAV period.

        end_date:
            Optional end of the requested NAV period.

    Returns historical NAV observations ordered newest first.
    """

    response = tools.get_nav_history(
        scheme_code=scheme_code,
        start_date=start_date,
        end_date=end_date,
    )

    return response.model_dump(
        mode="json",
        exclude_none=True,
    )


# ----------------------------------------------------------------------
# Entry Point
# ----------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()