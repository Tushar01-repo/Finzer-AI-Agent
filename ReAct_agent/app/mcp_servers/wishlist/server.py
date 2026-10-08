from __future__ import annotations

from typing import Any

from mcp.server import MCPServer

from app.mcp_servers.wishlist.tools import (
    add_to_wishlist,
    get_wishlist,
    is_in_wishlist,
    remove_from_wishlist,
)


# ======================================================================
# MCP Server
# ======================================================================

mcp = MCPServer(
    "finzer-wishlist-mcp"
)


# ======================================================================
# READ TOOLS
# ======================================================================


@mcp.tool(structured_output=False)
def wishlist_get(
    user_id: str,
) -> dict[str, Any]:
    """
    Return all assets currently stored in a user's wishlist.

    This is a read-only operation.
    """

    response = get_wishlist(
        user_id=user_id,
    )

    return response.model_dump(
        mode="json"
    )


@mcp.tool(structured_output=False)
def wishlist_check(
    user_id: str,
    asset_type: str,
    asset_id: str,
) -> dict[str, Any]:
    """
    Check whether a specific asset exists in a user's wishlist.

    This is a read-only operation.

    asset_type examples:
        MUTUAL_FUND
        GOLD
    """

    response = is_in_wishlist(
        user_id=user_id,
        asset_type=asset_type,
        asset_id=asset_id,
    )

    return response.model_dump(
        mode="json"
    )


# ======================================================================
# WRITE TOOLS
# ======================================================================


@mcp.tool(structured_output=False)
def wishlist_add(
    user_id: str,
    asset_type: str,
    asset_id: str,
    asset_name: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Add an asset to a user's wishlist.

    This is a state-changing WRITE operation.

    The operation is idempotent:
        created=True  -> new item created
        created=False -> item already existed

    Future execution governance may require authorization before this
    tool is called.
    """

    response = add_to_wishlist(
        user_id=user_id,
        asset_type=asset_type,
        asset_id=asset_id,
        asset_name=asset_name,
        metadata=metadata,
    )

    return response.model_dump(
        mode="json"
    )


@mcp.tool(structured_output=False)
def wishlist_remove(
    user_id: str,
    asset_type: str,
    asset_id: str,
) -> dict[str, Any]:
    """
    Remove an asset from a user's wishlist.

    This is a state-changing WRITE operation.

    The operation is idempotent:
        removed=True  -> existing item removed
        removed=False -> item was already absent

    Future execution governance may require authorization before this
    tool is called.
    """

    response = remove_from_wishlist(
        user_id=user_id,
        asset_type=asset_type,
        asset_id=asset_id,
    )

    return response.model_dump(
        mode="json"
    )


# ======================================================================
# Entrypoint
# ======================================================================


if __name__ == "__main__":
    mcp.run()