import os

import requests
from dotenv import load_dotenv


load_dotenv()

BASE_URL = "https://newsdata.io/api/1/latest"


def main() -> None:
    print("=" * 80)
    print("NEWSDATA.IO TEST")
    print("=" * 80)
    print()

    api_key = os.getenv("NEWSDATA_API_KEY")

    if not api_key:
        print("ERROR: NEWSDATA_API_KEY is not configured.")
        return

    params = {
        "apikey": api_key,
        "q": "TCS",
        "country": "in",
        "language": "en",
        "category": "business",
        "timeframe": "48",
    }

    print("Endpoint : /latest")
    print("Query    : TCS")
    print("Country  : India")
    print("Language : English")
    print("Category : Business")
    print()

    try:
        response = requests.get(
            BASE_URL,
            params=params,
            timeout=20,
        )

        print(f"HTTP status : {response.status_code}")
        print()

        response.raise_for_status()

        data = response.json()

    except requests.RequestException as exc:
        print(f"Request failed: {exc}")
        return

    except ValueError:
        print("Response was not valid JSON.")
        print(response.text[:2000])
        return

    print(f"API status   : {data.get('status')}")
    print(f"Total results: {data.get('totalResults')}")
    print()

    results = data.get("results", [])

    print(f"Articles returned: {len(results)}")
    print()

    if not results:
        print("No articles returned.")
        print()
        print("Full response:")
        print(data)
        return

    print("-" * 80)
    print("ARTICLES")
    print("-" * 80)

    for index, article in enumerate(results, start=1):
        print(f"\n[{index}]")
        print(f"Title       : {article.get('title')}")
        print(f"Source      : {article.get('source_name')}")
        print(f"Published   : {article.get('pubDate')}")
        print(f"URL         : {article.get('link')}")
        print(f"Description : {article.get('description')}")

        content = article.get("content")
        if content:
            print(f"Content     : {content[:500]}")

    print()
    print("=" * 80)


if __name__ == "__main__":
    main()