from pathlib import Path

from app.config.feed_registry import FeedRegistry
from app.services.google_search_news_parser import GoogleSearchNewsParser
from app.services.google_search_news_provider import GoogleSearchNewsProvider


def main() -> None:
    # Resolve paths relative to ingestion_service/
    base_dir = Path(__file__).resolve().parents[1]
    feeds_config = base_dir / "app" / "config" / "feeds.yaml"

    # Load feed configuration
    registry = FeedRegistry(feeds_config)
    feed = registry.get("company_tcs")

    # Initialize Google Search News provider
    provider = GoogleSearchNewsProvider(delay_seconds=0)

    # Initialize parser
    parser = GoogleSearchNewsParser()

    print("=" * 70)
    print("Google Search News Test")
    print("=" * 70)

    print(f"Feed ID : {feed['feed_id']}")
    print(f"Query   : {feed['query']}")
    print()

    # Fetch Google Search News HTML
    print("Fetching Google Search News...")
    html = provider.search(feed)

    print(f"Received HTML: {len(html)} characters")

    # Save raw HTML for inspection
    html_path = Path("/tmp/google_search.html")

    with html_path.open("w", encoding="utf-8") as file:
        file.write(html)

    print(f"Saved HTML to: {html_path}")
    print()

    # Parse results
    print("Parsing search results...")
    results = parser.parse(html)

    print(f"Articles discovered: {len(results)}")
    print()

    # Display parsed results
    if not results:
        print("No articles were discovered.")
        print()
        print("You can inspect the raw HTML with:")
        print(f"  less {html_path}")
        print()
        print("Or search for TCS-related content with:")
        print(
            f'  grep -i -E "TCS|Tata Consultancy|Reuters|'
            f'Moneycontrol|Economic Times|Business Standard" {html_path} | head -30'
        )
        return

    print("-" * 70)

    for index, result in enumerate(results[:10], start=1):
        print(f"{index}. {result.title}")
        print(f"   URL       : {result.url}")
        print(f"   Source    : {result.source}")
        print(f"   Published : {result.published_text}")
        print()

    print("=" * 70)


if __name__ == "__main__":
    main()