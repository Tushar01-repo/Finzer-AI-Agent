
"""MCP response adapter for Finzer Entity Lookup.

Phase 3.4 — Convert MCP search results into the
canonical EntityLookupService input format.

This adapter performs no network calls.
Python 3.10+.
"""

from __future__ import annotations

import json
from typing import Any


class MCPLookupAdapter:
    """Normalize mutual fund MCP responses."""

    @staticmethod
    def normalize_search_response(
        response: Any,
    ) -> dict[str, Any]:
        """Normalize an MCP result into a lookup response.

        Supports:
        - ToolResponse dictionaries
        - MCP CallToolResult objects
        - JSON-encoded MCP text content

        Rejects unsuccessful or malformed responses.
        """

        if hasattr(response, "model_dump"):
            response = response.model_dump(
                mode="json",
                exclude_none=True,
            )

        if not isinstance(response, dict):
            return {
                "isError": True,
                "message": "Unsupported MCP response type.",
            }

        if response.get("isError") is True:
            return {
                "isError": True,
                "message": "MCP tool execution failed.",
            }

        # Handle an MCP CallToolResult content wrapper.
        if "content" in response:

            structured = response.get("structuredContent")

            if isinstance(structured, dict):
                return (
                    MCPLookupAdapter.normalize_search_response(
                        structured
                    )
                )

            content = response["content"]

            if not isinstance(content, list):
                return {
                    "isError": True,
                    "message": "Invalid MCP content.",
                }

            for item in content:

                if not isinstance(item, dict):
                    continue

                text = item.get("text")

                if not isinstance(text, str):
                    continue

                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    continue

                return (
                    MCPLookupAdapter.normalize_search_response(
                        parsed
                    )
                )

            return {
                "isError": True,
                "message": "No valid JSON MCP content.",
            }

        # Handle our MutualFundTools ToolResponse.
        if response.get("status") == "error":
            return {
                "isError": True,
                "message": "Mutual fund lookup failed.",
                "error": response.get("error"),
            }

        if response.get("status") == "success":

            data = response.get("data")

            if not isinstance(data, list):
                return {
                    "isError": True,
                    "message": "Invalid mutual fund search data.",
                }

            return {"data": data}

        return {
            "isError": True,
            "message": "Unrecognized mutual fund MCP response.",
        }
