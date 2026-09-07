from abc import ABC, abstractmethod
from typing import List

from app.models.discovered_article import DiscoveredArticle


class NewsDiscoveryProvider(ABC):
    """
    Abstract interface for news discovery providers.

    Every news provider must implement this interface.
    The rest of the application should depend on this
    abstraction instead of a specific provider.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the unique provider name.

        Example:
            "newsdata"
        """
        pass

    @abstractmethod
    def discover(
        self,
        query: str,
        max_articles: int,
    ) -> List[DiscoveredArticle]:
        """
        Discover news articles for the given query.

        Parameters
        ----------
        query:
            Search query sent to the provider.

        max_articles:
            Maximum number of articles to return.

        Returns
        -------
        List[DiscoveredArticle]
            Provider-independent article objects.
        """
        pass