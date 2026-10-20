"""MCP stdio adapter for FinzerToolExecutor.

Initial scope: finzer-gold-mcp. Each invocation opens and closes a session.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClientError(RuntimeError):
    """Raised when MCP transport or tool execution fails."""


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SERVER_MODULES = {
    "finzer-gold-mcp": "app.mcp_servers.gold.server",
    "finzer-mutual-fund-mcp": "app.mcp_servers.mutual_fund.server",
    "finzer-wishlist-mcp": "app.mcp_servers.wishlist.server"
}


def _extract_payload(result: Any) -> Any:
    """Decode structured MCP output or JSON carried in TextContent."""
    structured = getattr(result, "structured_content", None)
    if structured is None:
        structured = getattr(result, "structuredContent", None)
    if structured is not None:
        if isinstance(structured, dict) and set(structured) == {"result"}:
            return structured["result"]
        return structured

    texts = [
        item.text
        for item in (result.content or [])
        if getattr(item, "type", None) == "text" and getattr(item, "text", None)
    ]
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except json.JSONDecodeError:
            return texts[0]
    if texts:
        return texts
    return [item.model_dump(mode="json") for item in (result.content or [])]


async def call_mcp_tool_async(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> Any:
    """Invoke a tool on an allowlisted local MCP server."""
    if server_name not in _SERVER_MODULES:
        raise MCPClientError(f"MCP server is not configured: {server_name}")
    if not isinstance(arguments, dict):
        raise TypeError("MCP tool arguments must be a dictionary")

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", _SERVER_MODULES[server_name]],
        cwd=str(_PROJECT_ROOT),
        env=os.environ.copy(),
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)

    if result.is_error:
        messages = [
            getattr(item, "text", "")
            for item in (result.content or [])
        ]
        detail = "; ".join(filter(None, messages)) or "unknown MCP error"
        raise MCPClientError(f"MCP tool {tool_name} failed: {detail}")

    # Business/provider errors (payload status='error') remain structured
    # responses, rather than being mislabeled as MCP transport failures.
    return _extract_payload(result)


def call_mcp_tool(
    server_name: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> Any:
    """Synchronous callback for FinzerToolExecutor."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(call_mcp_tool_async(server_name, tool_name, arguments))
    raise MCPClientError(
        "call_mcp_tool cannot run inside an active event loop; "
        "await call_mcp_tool_async instead"
    )
