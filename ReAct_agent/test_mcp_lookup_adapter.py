
"""Functional tests for Finzer MCP Lookup Adapter.

Run:
    python -m pytest .\\test_mcp_lookup_adapter.py -v
"""

import json

import pytest

from app.agent.entities import MCPLookupAdapter
from app.agent.entities import (
    EntityLookupService,
    LookupStatus,
)


@pytest.fixture
def adapter():
    return MCPLookupAdapter()


@pytest.fixture
def success_response():
    return {
        "status": "success",
        "data": [
            {
                "scheme_code": 125497,
                "scheme_name": "SBI Small Cap Fund",
            }
        ],
    }


def test_successful_tool_response(adapter, success_response):
    result = adapter.normalize_search_response(success_response)

    assert result == {"data": success_response["data"]}


def test_empty_success_response(adapter):
    result = adapter.normalize_search_response(
        {"status": "success", "data": []}
    )

    assert result == {"data": []}


def test_business_error_response(adapter):
    result = adapter.normalize_search_response(
        {
            "status": "error",
            "error": {
                "type": "UPSTREAM_TIMEOUT",
                "message": "Request timed out.",
                "retryable": True,
            },
        }
    )

    assert result["isError"] is True
    assert result["error"]["type"] == "UPSTREAM_TIMEOUT"


def test_mcp_execution_error(adapter):
    result = adapter.normalize_search_response(
        {
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": "Tool execution failed.",
                }
            ],
        }
    )

    assert result["isError"] is True


def test_mcp_json_content(adapter, success_response):
    result = adapter.normalize_search_response(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(success_response),
                }
            ]
        }
    )

    assert result == {"data": success_response["data"]}


def test_mcp_structured_content(adapter, success_response):
    result = adapter.normalize_search_response(
        {
            "content": [],
            "structuredContent": success_response,
        }
    )

    assert result == {"data": success_response["data"]}


def test_invalid_mcp_json(adapter):
    result = adapter.normalize_search_response(
        {
            "content": [
                {
                    "type": "text",
                    "text": "not valid json",
                }
            ]
        }
    )

    assert result["isError"] is True


def test_invalid_content_type(adapter):
    result = adapter.normalize_search_response(
        {"content": "invalid"}
    )

    assert result["isError"] is True


def test_missing_data(adapter):
    result = adapter.normalize_search_response(
        {"status": "success"}
    )

    assert result["isError"] is True


def test_invalid_data_type(adapter):
    result = adapter.normalize_search_response(
        {"status": "success", "data": "invalid"}
    )

    assert result["isError"] is True


def test_unsupported_response(adapter):
    result = adapter.normalize_search_response(
        {"unexpected": "value"}
    )

    assert result["isError"] is True


def test_non_dictionary_response(adapter):
    result = adapter.normalize_search_response(
        "invalid response"
    )

    assert result["isError"] is True


def test_adapter_to_lookup_integration(
    adapter,
    success_response,
):
    normalized = adapter.normalize_search_response(
        success_response
    )

    result = EntityLookupService().resolve_mutual_fund(
        "SBI Small Cap Fund",
        normalized,
    )

    assert result.status == LookupStatus.RESOLVED
    assert result.entity.canonical_id == "125497"


def test_adapter_error_to_lookup_integration(adapter):
    normalized = adapter.normalize_search_response(
        {
            "status": "error",
            "error": {
                "type": "UPSTREAM_TIMEOUT",
                "message": "Request timed out.",
                "retryable": True,
            },
        }
    )

    result = EntityLookupService().resolve_mutual_fund(
        "SBI Small Cap Fund",
        normalized,
    )

    assert result.status == LookupStatus.INVALID_RESPONSE
    assert result.entity is None

