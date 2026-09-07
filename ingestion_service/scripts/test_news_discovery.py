from app.providers.news.newsdata import NewsDataProvider
from app.services.news_discovery_service import NewsDiscoveryService


def main() -> None:
    provider = NewsDataProvider()

    discovery_service = NewsDiscoveryService(
        provider=provider,
    )

    print(f"Provider: {provider.name}")
    print("Starting news discovery...\n")

    articles = discovery_service.discover(
        query="Tata Consultancy Services",
        max_articles=20,
    )

    print(f"Articles discovered: {len(articles)}")
    print("=" * 80)

    for index, article in enumerate(articles, start=1):
        print(f"\nArticle {index}")
        print(f"Title       : {article.title}")
        print(f"Source      : {article.source}")
        print(f"URL         : {article.url}")
        print(f"Published   : {article.published_at}")
        print(f"Authors     : {article.authors}")
        print(f"Description : {article.description}")
        print("-" * 80)


if __name__ == "__main__":
    main()