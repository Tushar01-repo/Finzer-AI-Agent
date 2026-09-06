from app.config.feed_registry import FeedRegistry
from app.services.google_search_news_parser import GoogleSearchNewsParser
from app.services.google_search_news_provider import GoogleSearchNewsProvider


def main() -> None:
    registry = FeedRegistry()
    feed = registry.get("company_tcs")

    provider = GoogleSearchNewsProvider(
        delay_seconds=0,
    )

    parser = GoogleSearchNewsParser()

    print(f"Searching for: {feed['query']}")

    html = provider.search(feed)

    print(f"Received HTML: {len(html)} characters")

    results = parser.parse(html)

    print(f"Articles discovered: {len(results)}")
    print()

    for index, result in enumerate(results[:10], start=1):
        print(f"{index}. {result.title}")
        print(f"   URL: {result.url}")
        print(f"   Source: {result.source}")
        print(f"   Published: {result.published_text}")
        print()


if __name__ == "__main__":
    main()