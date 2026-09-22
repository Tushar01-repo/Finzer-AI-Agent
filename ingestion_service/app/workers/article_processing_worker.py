import json
import signal
from typing import Any

import pika

from app.config.settings import settings
from app.queue.queue_topology import QueueTopology
from app.queue.retry_router import RetryRouter
from app.repositories.article_repository import ArticleRepository
from app.repositories.database import PostgresDatabase
from app.services.llm_analyzer import ArticleAnalyzer


class ArticleProcessingWorker:
    """
    RabbitMQ worker responsible for processing articles.

    Flow:

        RabbitMQ
            ↓
        article.processing
            ↓
        fetch article from PostgreSQL
            ↓
        ArticleAnalyzer
            ↓
        save LLM analysis
            ↓
        ACK message

    Invalid and irrelevant articles are still considered
    successfully processed and are ACKed.

    Processing failures are NACKed without requeue to avoid
    infinite poison-message loops.
    """

    def __init__(
        self,
        rabbitmq_url: str | None = None,
        queue_name: str | None = None,
    ):
        self.rabbitmq_url = (
            rabbitmq_url
            if rabbitmq_url is not None
            else settings.RABBITMQ_URL
        )

        self.queue_name = (
            queue_name
            if queue_name is not None
            else settings.ARTICLE_QUEUE
        )

        self.embedding_queue_name = settings.ARTICLE_EMBEDDING_QUEUE
        self.retry_router = RetryRouter(
            retry_queue_prefix=settings.ARTICLE_RETRY_QUEUE,
            dlq=settings.ARTICLE_DLQ,
            retry_delays_ms=settings.ARTICLE_RETRY_DELAYS_MS,
        )

        if not self.rabbitmq_url:
            raise ValueError(
                "RABBITMQ_URL is not configured."
            )

        if not self.queue_name:
            raise ValueError(
                "ARTICLE_QUEUE is not configured."
            )

        if not self.embedding_queue_name:
            raise ValueError(
                "ARTICLE_EMBEDDING_QUEUE is not configured."
            )

        self.database = PostgresDatabase()

        self.repository = ArticleRepository(
            database=self.database
        )

        self.analyzer = ArticleAnalyzer()

        self.connection: pika.BlockingConnection | None = None
        self.channel = None
        self._stopping = False

    # ---------------------------------------------------------
    # RabbitMQ connection
    # ---------------------------------------------------------

    def _create_connection(
        self,
    ) -> pika.BlockingConnection:
        """
        Create RabbitMQ connection.

        The worker performs potentially long LLM operations,
        therefore the heartbeat must not be too aggressive.
        """

        parameters = pika.URLParameters(
            self.rabbitmq_url
        )

        # LLM inference can take significant time.
        parameters.heartbeat = 600
        parameters.blocked_connection_timeout = 300

        return pika.BlockingConnection(
            parameters
        )

    # ---------------------------------------------------------
    # Safe RabbitMQ operations
    # ---------------------------------------------------------

    def _safe_ack(
        self,
        channel,
        delivery_tag,
    ) -> bool:
        """
        ACK message only if RabbitMQ channel is still open.

        ACK failure must NOT be treated as an article-processing
        failure because the article may already have been saved
        successfully to PostgreSQL.
        """

        if channel is None or not channel.is_open:
            print(
                "RabbitMQ channel is closed; "
                "message could not be ACKed."
            )
            return False

        try:
            channel.basic_ack(
                delivery_tag=delivery_tag
            )

            print(
                "RabbitMQ message ACKed."
            )

            return True

        except (
            pika.exceptions.AMQPError,
            OSError,
        ) as exc:
            print(
                "RabbitMQ ACK failed: "
                f"{exc}"
            )

            return False

    def _safe_nack(
        self,
        channel,
        delivery_tag,
        *,
        requeue: bool,
    ) -> bool:
        """
        NACK message only if the RabbitMQ channel is open.
        """

        if channel is None or not channel.is_open:
            print(
                "RabbitMQ channel is closed; "
                "message could not be NACKed."
            )
            return False

        try:
            channel.basic_nack(
                delivery_tag=delivery_tag,
                requeue=requeue,
            )

            print(
                "RabbitMQ message NACKed "
                f"(requeue={requeue})."
            )

            return True

        except (
            pika.exceptions.AMQPError,
            OSError,
        ) as exc:
            print(
                "RabbitMQ NACK failed: "
                f"{exc}"
            )

            return False

    def _publish_embedding_message(
        self,
        channel,
        article_key: str,
    ) -> None:
        """
        Publish a successfully analyzed article to the embedding queue.

        Only the article_key is sent. The embedding worker will fetch
        the canonical article data from PostgreSQL.
        """

        if channel is None or not channel.is_open:
            raise RuntimeError(
                "RabbitMQ channel is closed; embedding message "
                "cannot be published."
            )

        channel.queue_declare(
            queue=self.embedding_queue_name,
            durable=True,
        )

        payload = {
            "article_key": article_key,
        }

        channel.basic_publish(
            exchange="",
            routing_key=self.embedding_queue_name,
            body=json.dumps(payload),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )

        print(
            "Article published to embedding queue: "
            f"{self.embedding_queue_name}"
        )

    # ---------------------------------------------------------
    # Start worker
    # ---------------------------------------------------------

    def start(
        self,
    ) -> None:
        """
        Start consuming article-processing messages.
        """

        print("=" * 70)
        print("Finzer Article Processing Worker")
        print("=" * 70)

        print(
            f"Queue: {self.queue_name}"
        )

        print(
            f"Embedding queue: {self.embedding_queue_name}"
        )

        # print(
        #     f"LLM: {self.analyzer.base_url}"
        # )

        print("LLM: configured through LLM Router")

        print(
            "Relevance threshold: "
            f"{self.analyzer.relevance_threshold}"
        )

        print()

        self.connection = (
            self._create_connection()
        )

        self.channel = (
            self.connection.channel()
        )

        QueueTopology(rabbitmq_url=self.rabbitmq_url).declare()
        self.channel.confirm_delivery()

        self.channel.queue_declare(
            queue=self.queue_name,
            durable=True,
        )

        self.channel.queue_declare(
            queue=self.embedding_queue_name,
            durable=True,
        )

        # Only process one article at a time.
        self.channel.basic_qos(
            prefetch_count=1
        )

        self.channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=self._on_message,
            auto_ack=False,
        )

        self._register_signal_handlers()

        print(
            "Waiting for article messages..."
        )

        print(
            "Press CTRL+C to stop."
        )

        print()

        try:
            self.channel.start_consuming()

        except KeyboardInterrupt:
            self.stop()

        except pika.exceptions.AMQPError as exc:
            print(
                "RabbitMQ consumer connection failed: "
                f"{exc}"
            )

        finally:
            self.stop()

    # ---------------------------------------------------------
    # RabbitMQ callback
    # ---------------------------------------------------------

    def _on_message(
        self,
        channel,
        method,
        properties,
        body: bytes,
    ) -> None:
        """
        RabbitMQ callback for one article message.
        """

        delivery_tag = (
            method.delivery_tag
        )

        article_key: str | None = None

        # -----------------------------------------------------
        # Parse message
        # -----------------------------------------------------

        try:
            message = self._parse_message(
                body
            )

            article_key = message[
                "article_key"
            ]

            feed_id = message[
                "feed_id"
            ]

            feed_target = message[
                "feed_target"
            ]

            feed_description = message.get(
                "feed_description"
            )

        except ValueError as exc:
            print(
                f"Invalid RabbitMQ message: {exc}"
            )

            outcome = self.retry_router.route_failure(
                channel,
                delivery_tag=delivery_tag,
                properties=properties,
                body=body,
                retryable=False,
                error=exc,
            )
            print(f"Invalid message routed to {outcome}.")

            print()
            return

        print("=" * 70)

        print(
            f"Received article: {article_key}"
        )

        print(
            f"Feed: {feed_id}"
        )

        # -----------------------------------------------------
        # Article processing
        # -----------------------------------------------------

        try:
            article = (
                self.repository.get_by_key(
                    article_key
                )
            )

            # -------------------------------------------------
            # Missing article
            # -------------------------------------------------

            if article is None:
                print(
                    "Article does not exist "
                    "in PostgreSQL."
                )

                self._safe_ack(
                    channel,
                    delivery_tag,
                )

                print()
                return

            print(
                f"Title: {article.title}"
            )

            print(
                "Current status: "
                f"{article.processing_status}"
            )

            # -------------------------------------------------
            # Idempotency guard
            # -------------------------------------------------

            if article.processing_status == "analyzed":
                print(
                    "Article is already analyzed. "
                    "Ensuring it is queued for embedding."
                )

                self._publish_embedding_message(
                    channel,
                    article_key,
                )

                self._safe_ack(
                    channel,
                    delivery_tag,
                )

                print()
                return

            if article.processing_status in {
                "irrelevant",
                "invalid",
                "embedded",
            }:
                print(
                    "Article has already been processed. "
                    "ACKing duplicate message."
                )

                self._safe_ack(
                    channel,
                    delivery_tag,
                )

                print()
                return

            # -------------------------------------------------
            # Validate content
            # -------------------------------------------------

            if (
                not article.content
                or not article.content.strip()
            ):
                print(
                    "Article contains no usable content."
                )

                self.repository.update_processing_status(
                    article_key,
                    "invalid",
                )

                self._safe_ack(
                    channel,
                    delivery_tag,
                )

                print()
                return

            print(
                "Content length: "
                f"{len(article.content)}"
            )

            # -------------------------------------------------
            # Mark processing
            # -------------------------------------------------

            self.repository.update_processing_status(
                article_key,
                "processing",
            )

            # -------------------------------------------------
            # LLM analysis
            # -------------------------------------------------

            print(
                "Sending article to LLM..."
            )

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

            # -------------------------------------------------
            # Debug: print LLM response
            # -------------------------------------------------

            print()
            print("=" * 70)
            print("LLM RESPONSE")
            print("=" * 70)

            try:
                print(
                    json.dumps(
                        result.raw_response,
                        indent=2,
                        ensure_ascii=False,
                        default=str,
                    )
                )
            except Exception as debug_exc:
                print(
                    "Unable to pretty-print LLM response: "
                    f"{debug_exc}"
                )
                print(result.raw_response)

            print("=" * 70)
            print()

            # -------------------------------------------------
            # Determine final status
            # -------------------------------------------------

            if not result.is_valid_article:
                final_status = "invalid"

            elif result.is_relevant:
                final_status = "analyzed"

            else:
                final_status = "irrelevant"

            # -------------------------------------------------
            # Persist result
            # -------------------------------------------------

            self.repository.save_article_analysis(
                article_key=article_key,
                is_valid_article=(
                    result.is_valid_article
                ),
                relevance_score=(
                    result.relevance_score
                ),
                is_relevant=(
                    result.is_relevant
                ),
                relevance_reason=(
                    result.relevance_reason
                ),
                summary=result.summary,
                key_facts=(
                    result.key_facts
                ),
                companies_mentioned=(
                    result.companies_mentioned
                ),
                market_impact=(
                    result.market_impact
                ),
                llm_analysis=(
                    result.raw_response
                ),
            )

            # -------------------------------------------------
            # Queue relevant articles for embedding
            # -------------------------------------------------

            if final_status == "analyzed":
                self._publish_embedding_message(
                    channel,
                    article_key,
                )

            # -------------------------------------------------
            # Result logging
            # -------------------------------------------------

            print()
            print(
                "Analysis completed"
            )
            print(
                "------------------"
            )

            print(
                "Valid: "
                f"{result.is_valid_article}"
            )

            print(
                "Relevance: "
                f"{result.relevance_score}"
            )

            print(
                "Relevant: "
                f"{result.is_relevant}"
            )

            print(
                f"Status: {final_status}"
            )

        except Exception as exc:
            # IMPORTANT:
            #
            # Only actual article processing failures enter here.
            # ACK/NACK operations happen outside this block.

            print(
                "Article processing failed: "
                f"{exc}"
            )

            if article_key:
                try:
                    self.repository.update_processing_status(
                        article_key,
                        "failed",
                    )

                except Exception as status_exc:
                    print(
                        "Unable to update article "
                        "status: "
                        f"{status_exc}"
                    )

            outcome = self.retry_router.route_failure(
                channel,
                delivery_tag=delivery_tag,
                properties=properties,
                body=body,
                retryable=True,
                error=exc,
            )
            print(f"Processing failure routed to {outcome}.")

            print()
            return

        # -----------------------------------------------------
        # ACK only after successful processing
        # -----------------------------------------------------

        self._safe_ack(
            channel,
            delivery_tag,
        )

        print()

    # ---------------------------------------------------------
    # Message parsing
    # ---------------------------------------------------------

    @staticmethod
    def _parse_message(
        body: bytes,
    ) -> dict[str, Any]:
        """
        Decode and validate RabbitMQ message.
        """

        try:
            message = json.loads(
                body.decode("utf-8")
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise ValueError(
                "Message is not valid JSON."
            ) from exc

        if not isinstance(
            message,
            dict,
        ):
            raise ValueError(
                "Message must be a JSON object."
            )

        required_fields = [
            "article_key",
            "feed_id",
            "feed_target",
        ]

        missing_fields = [
            field
            for field in required_fields
            if not message.get(field)
        ]

        if missing_fields:
            raise ValueError(
                "Missing required fields: "
                + ", ".join(
                    missing_fields
                )
            )

        return message

    # ---------------------------------------------------------
    # Shutdown handling
    # ---------------------------------------------------------

    def _register_signal_handlers(
        self,
    ) -> None:
        """
        Gracefully stop on CTRL+C / process termination.
        """

        signal.signal(
            signal.SIGINT,
            self._handle_shutdown_signal,
        )

        if hasattr(
            signal,
            "SIGTERM",
        ):
            signal.signal(
                signal.SIGTERM,
                self._handle_shutdown_signal,
            )

    def _handle_shutdown_signal(
        self,
        signum,
        frame,
    ) -> None:
        print()

        print(
            "Shutdown signal received."
        )

        self.stop()

    def stop(
        self,
    ) -> None:
        """
        Gracefully stop RabbitMQ consumer.
        """

        if self._stopping:
            return

        self._stopping = True

        print(
            "Stopping article worker..."
        )

        try:
            if (
                self.channel
                and self.channel.is_open
            ):
                self.channel.stop_consuming()

        except Exception:
            pass

        try:
            if (
                self.connection
                and self.connection.is_open
            ):
                self.connection.close()

        except Exception:
            pass

        print(
            "Article worker stopped."
        )


def main() -> None:
    worker = ArticleProcessingWorker()

    worker.start()


if __name__ == "__main__":
    main()
