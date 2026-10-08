from __future__ import annotations

import json
import os

import requests


BASE_URL = "https://api.goldprice.dev"


def print_response(title: str, response: requests.Response) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

    print("Status:", response.status_code)
    print("URL:", response.url)

    try:
        data = response.json()
        print(json.dumps(data, indent=2))
    except ValueError:
        print(response.text)


def main() -> None:
    api_key = os.getenv("GOLDPRICE_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GOLDPRICE_API_KEY environment variable is not set."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }

    print("=" * 70)
    print("FINZER - GOLDPRICE.DEV API DISCOVERY")
    print("=" * 70)

    # --------------------------------------------------------------
    # TEST 1 - Spot gold price
    # --------------------------------------------------------------

    response = requests.get(
        f"{BASE_URL}/v1/spot/XAU-USD-SPOT",
        headers=headers,
        timeout=20,
    )

    print_response(
        "[1] Gold spot price",
        response,
    )

    # --------------------------------------------------------------
    # TEST 2 - Carat prices
    # --------------------------------------------------------------

    response = requests.get(
        f"{BASE_URL}/v1/carat",
        headers=headers,
        timeout=20,
    )

    print_response(
        "[2] Gold carat prices",
        response,
    )

    # --------------------------------------------------------------
    # TEST 3 - Account usage
    # --------------------------------------------------------------

    response = requests.get(
        f"{BASE_URL}/v1/account/usage",
        headers=headers,
        timeout=20,
    )

    print_response(
        "[3] API usage",
        response,
    )

    # --------------------------------------------------------------
    # TEST 4 - Historical gold price bars
    # --------------------------------------------------------------

    response = requests.get(
        f"{BASE_URL}/v1/bars",
        headers=headers,
        params={
            "symbol": "XAU-USD-SPOT",
            "interval": "1d",
            "from": "2026-09-03",
            "to": "2026-09-05",
        },
        timeout=20,
    )

    print_response(
        "[4] Historical gold price bars",
        response,
    )

    
    # --------------------------------------------------------------
    # TEST 5 - Gold conversion
    # --------------------------------------------------------------

    response = requests.get(
        f"{BASE_URL}/v1/convert",
        headers=headers,
        params={
            "from": "XAU",
            "to": "INR",
            "amount": 10,
            "unit": "gram",
        },
        timeout=20,
    )

    print_response(
        "[5] Gold conversion - 10 grams XAU to INR",
        response,
    )


if __name__ == "__main__":
    main()