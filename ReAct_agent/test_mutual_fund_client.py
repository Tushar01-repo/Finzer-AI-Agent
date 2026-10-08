from __future__ import annotations

from pprint import pprint

from app.mcp_servers.mutual_fund.client import (
    MFAPIClient,
    MFAPIError,
)


def main() -> None:
    client = MFAPIClient(timeout_seconds=20)

    print("=" * 70)
    print("FINZER - MFAPI CLIENT TEST")
    print("=" * 70)

    # ------------------------------------------------------------
    # TEST 1: Search
    # ------------------------------------------------------------

    print("\n[1] Searching for: SBI Small Cap")

    search_results = client.search_mutual_funds("SBI Small Cap")

    print(f"Found {len(search_results)} result(s)")

    for fund in search_results[:5]:
        pprint(fund.model_dump())

    if not search_results:
        print("\nNo matching mutual funds found.")
        return

    # Prefer the exact scheme we previously used if MFAPI returns it.
    preferred_scheme_code = 125497

    selected_fund = next(
        (
            fund
            for fund in search_results
            if fund.scheme_code == preferred_scheme_code
        ),
        search_results[0],
    )

    scheme_code = selected_fund.scheme_code

    print("\nSelected fund:")
    pprint(selected_fund.model_dump())

    print(f"\nUsing scheme code: {scheme_code}")

    # ------------------------------------------------------------
    # TEST 2: Fund details
    # ------------------------------------------------------------

    print("\n" + "=" * 70)
    print("[2] Getting mutual fund details")
    print("=" * 70)

    details = client.get_mutual_fund_details(scheme_code)

    pprint(details.model_dump())

    # ------------------------------------------------------------
    # TEST 3: Latest NAV
    # ------------------------------------------------------------

    print("\n" + "=" * 70)
    print("[3] Getting latest NAV")
    print("=" * 70)

    latest_nav = client.get_latest_nav(scheme_code)

    pprint(latest_nav.model_dump())

    # ------------------------------------------------------------
    # TEST 4: NAV history
    # ------------------------------------------------------------

    print("\n" + "=" * 70)
    print("[4] Getting NAV history")
    print("=" * 70)

    history = client.get_nav_history(scheme_code)

    print(f"Scheme: {history.scheme_name}")
    print(f"Total observations returned: {history.count}")

    print("\nFirst 5 observations:")

    for observation in history.observations[:5]:
        pprint(observation.model_dump())

    # ------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------

    print("\n" + "=" * 70)
    print("ALL MFAPI CLIENT TESTS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()

    except MFAPIError as exc:
        print("\nMFAPI CLIENT ERROR")
        print(type(exc).__name__)
        print(str(exc))
        raise

    except Exception as exc:
        print("\nUNEXPECTED ERROR")
        print(type(exc).__name__)
        print(str(exc))
        raise