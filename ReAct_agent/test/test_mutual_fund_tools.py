from __future__ import annotations

from pprint import pprint

from app.mcp_servers.mutual_fund.tools import MutualFundTools


def print_response(title: str, response) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

    pprint(
        response.model_dump(
            mode="json",
            exclude_none=True,
        )
    )


def assert_success(response, test_name: str) -> None:
    assert response.status == "success", (
        f"{test_name} failed: "
        f"{response.error.model_dump() if response.error else 'unknown error'}"
    )

    assert response.data is not None, (
        f"{test_name} returned success but data is None."
    )


def assert_error(
    response,
    expected_type: str,
    test_name: str,
) -> None:
    assert response.status == "error", (
        f"{test_name} expected an error response."
    )

    assert response.error is not None, (
        f"{test_name} returned error status without ToolError."
    )

    assert response.error.type == expected_type, (
        f"{test_name}: expected error type "
        f"{expected_type!r}, got {response.error.type!r}."
    )


def main() -> None:
    tools = MutualFundTools()

    print("=" * 70)
    print("FINZER - MUTUAL FUND TOOL LAYER TEST")
    print("=" * 70)

    # ============================================================
    # TEST 1
    # Search mutual funds
    # ============================================================

    response = tools.search_mutual_funds(
        query="SBI Small Cap"
    )

    print_response(
        "[1] Search mutual funds",
        response,
    )

    assert_success(
        response,
        "Search mutual funds",
    )

    assert len(response.data) > 0

    preferred_scheme_code = 125497

    selected_fund = next(
        (
            fund
            for fund in response.data
            if fund.scheme_code == preferred_scheme_code
        ),
        response.data[0],
    )

    scheme_code = selected_fund.scheme_code

    print(
        f"\nSelected scheme: "
        f"{selected_fund.scheme_name} ({scheme_code})"
    )

    # ============================================================
    # TEST 2
    # Fund details
    # ============================================================

    response = tools.get_mutual_fund_details(
        scheme_code=scheme_code
    )

    print_response(
        "[2] Mutual fund details",
        response,
    )

    assert_success(
        response,
        "Mutual fund details",
    )

    assert response.data.scheme_code == scheme_code

    # ============================================================
    # TEST 3
    # Latest NAV
    # ============================================================

    response = tools.get_latest_nav(
        scheme_code=scheme_code
    )

    print_response(
        "[3] Latest NAV",
        response,
    )

    assert_success(
        response,
        "Latest NAV",
    )

    assert response.data.scheme_code == scheme_code
    assert response.data.nav >= 0

    # ============================================================
    # TEST 4
    # NAV history with ISO dates
    #
    # This is the date format our future ReAct agent should use.
    # ============================================================

    response = tools.get_nav_history(
        scheme_code=scheme_code,
        start_date="2026-09-01",
        end_date="2026-09-30",
    )

    print_response(
        "[4] NAV history - ISO date range",
        response,
    )

    assert_success(
        response,
        "NAV history",
    )

    print(
        "\nNAV observations returned:",
        response.data.count,
    )

    # ============================================================
    # TEST 5
    # Invalid scheme code
    # ============================================================

    response = tools.get_latest_nav(
        scheme_code=-1
    )

    print_response(
        "[5] Invalid scheme code",
        response,
    )

    assert_error(
        response,
        "VALIDATION_ERROR",
        "Invalid scheme code",
    )

    # ============================================================
    # TEST 6
    # Invalid date
    # ============================================================

    response = tools.get_nav_history(
        scheme_code=scheme_code,
        start_date="not-a-date",
        end_date="2026-09-30",
    )

    print_response(
        "[6] Invalid date",
        response,
    )

    assert_error(
        response,
        "VALIDATION_ERROR",
        "Invalid date",
    )

    # ============================================================
    # TEST 7
    # start_date > end_date
    # ============================================================

    response = tools.get_nav_history(
        scheme_code=scheme_code,
        start_date="2026-09-30",
        end_date="2026-09-01",
    )

    print_response(
        "[7] Invalid date range",
        response,
    )

    assert_error(
        response,
        "INVALID_DATE_RANGE",
        "Invalid date range",
    )

    # ============================================================
    # TEST 8
    # Empty search query
    # ============================================================

    response = tools.search_mutual_funds(
        query=""
    )

    print_response(
        "[8] Empty search query",
        response,
    )

    assert_error(
        response,
        "VALIDATION_ERROR",
        "Empty search query",
    )

    # ============================================================
    # Final summary
    # ============================================================

    print("\n" + "=" * 70)
    print("ALL MUTUAL FUND TOOL TESTS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()