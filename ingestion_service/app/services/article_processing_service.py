from app.repositories.article_repository import ArticleRepository
from app.services.llm_analyzer import ArticleAnalyzer


class ArticleProcessingService:
    """
    Processes pending articles through the LLM analyzer.

    Flow:
        pending article
            ↓
        LLM analysis
            ↓
        persist analysis
            ↓
        relevant article -> ready for embedding
        irrelevant/invalid -> stop processing
    """

    def __init__(
        self,
        repository: ArticleRepository,
        analyzer: ArticleAnalyzer,
    ):
        self.repository = repository
        self.analyzer = analyzer

    def process_pending_articles(
        self,
        *,
        feed_id: str,
        feed_target: str,
        feed_description: str,
        limit: int = 10,
    ) -> dict[str, int]:
        """
        Process pending articles from PostgreSQL.

        Returns basic processing statistics.
        """

        articles = self.repository.get_pending_articles(
            limit=limit
        )

        stats = {
            "fetched": len(articles),
            "processed": 0,
            "relevant": 0,
            "irrelevant": 0,
            "invalid": 0,
            "failed": 0,
        }

        for article in articles:
            try:
                self._process_article(
                    article=article,
                    feed_id=feed_id,
                    feed_target=feed_target,
                    feed_description=feed_description,
                )

                stats["processed"] += 1

                refreshed = self.repository.get_by_key(
                    article.article_key
                )

                if refreshed is None:
                    stats["failed"] += 1
                    continue

                if refreshed.processing_status == "analyzed":
                    stats["relevant"] += 1

                elif refreshed.processing_status == "irrelevant":
                    stats["irrelevant"] += 1

                elif refreshed.processing_status == "invalid":
                    stats["invalid"] += 1

            except Exception as exc:
                stats["failed"] += 1

                self.repository.update_processing_status(
                    article.article_key,
                    "failed",
                )

                print(
                    f"Article processing failed "
                    f"for {article.article_key}: {exc}"
                )

        return stats

    def _process_article(
        self,
        *,
        article,
        feed_id: str,
        feed_target: str,
        feed_description: str,
    ) -> None:
        """
        Process one article.
        """

        if not article.content or not article.content.strip():
            self.repository.update_processing_status(
                article.article_key,
                "invalid",
            )

            return

        result = self.analyzer.analyze(
            feed_id=feed_id,
            feed_target=feed_target,
            feed_description=feed_description,
            title=article.title,
            source=article.source,
            published_at=(
                article.published_at.isoformat()
                if article.published_at
                else None
            ),
            content=article.content,
        )

        self.repository.save_article_analysis(
            article_key=article.article_key,
            is_valid_article=result.is_valid_article,
            relevance_score=result.relevance_score,
            is_relevant=result.is_relevant,
            relevance_reason=result.relevance_reason,
            summary=result.summary,
            key_facts=result.key_facts,
            companies_mentioned=result.companies_mentioned,
            market_impact=result.market_impact,
            llm_analysis=result.raw_response,
        )