from app.models.discovered_article import DiscoveredArticle
from app.providers.news.base import NewsDiscoveryProvider


class NewsDiscoveryService:
    """
    Application-level service responsible for news discovery.

    This service depends only on the NewsDiscoveryProvider abstraction.
    It does not know which concrete provider is being used.

    Example providers:
        - NewsDataProvider
        - Future Provider B
        - Future Provider C

    Provider-specific logic must remain inside the provider
    implementation.
    """

    def __init__(
        self,
        provider: NewsDiscoveryProvider,
    ) -> None:
        self.provider = provider

    def discover(
        self,
        query: str,
        max_articles: int,
    ) -> list[DiscoveredArticle]:
        """
        Discover news articles using the configured provider.

        Parameters
        ----------
        query:
            Query used for news discovery.

        max_articles:
            Maximum number of articles to discover.

        Returns
        -------
        list[DiscoveredArticle]
            Provider-independent discovered articles.
        """

        if not query or not query.strip():
            return []

        if max_articles <= 0:
            return []

        return self.provider.discover(
            query=query.strip(),
            max_articles=max_articles,
        )