import json
import signal
from typing import Any

import pika
import requests

from app.config.settings import settings
from app.queue.queue_topology import QueueTopology
from app.queue.retry_router import RetryRouter
from app.repositories.article_repository import ArticleRepository
from app.repositories.database import PostgresDatabase


class ArticleEmbeddingWorker:
    """
    Consume article.embedding messages, generate embeddings through the
    dedicated embedding service, and persist them in PostgreSQL/pgvector.

    Only articles in the analyzed state are eligible for embedding.
    Duplicate messages for already-embedded articles are safely ACKed.
    """

    def __init__(
        self,
        rabbitmq_url: str | None = None,
        queue_name: str | None = None,
        embedding_service_url: str | None = None,
    ):
        self.rabbitmq_url = rabbitmq_url or settings.RABBITMQ_URL
        self.queue_name = queue_name or settings.ARTICLE_EMBEDDING_QUEUE
        self.embedding_service_url = (
            embedding_service_url or settings.EMBEDDING_SERVICE_URL
        )
        self.embedding_timeout = settings.EMBEDDING_REQUEST_TIMEOUT
        self.embedding_dimension = settings.EMBEDDING_DIMENSION
        self.embedding_model = settings.EMBEDDING_MODEL
        self.retry_router = RetryRouter(
            retry_queue_prefix=settings.ARTICLE_EMBEDDING_RETRY_QUEUE,
            dlq=settings.ARTICLE_EMBEDDING_DLQ,
            retry_delays_ms=settings.ARTICLE_RETRY_DELAYS_MS,
        )

        if not self.rabbitmq_url:
            raise ValueError("RABBITMQ_URL is not configured.")
        if not self.queue_name:
            raise ValueError("ARTICLE_EMBEDDING_QUEUE is not configured.")
        if not self.embedding_service_url:
            raise ValueError("EMBEDDING_SERVICE_URL is not configured.")
        if self.embedding_dimension <= 0:
            raise ValueError("EMBEDDING_DIMENSION must be greater than zero.")

        self.database = PostgresDatabase()
        self.repository = ArticleRepository(self.database)

        self.connection: pika.BlockingConnection | None = None
        self.channel = None
        self._stopping = False

    def _create_connection(self) -> pika.BlockingConnection:
        parameters = pika.URLParameters(self.rabbitmq_url)
        parameters.heartbeat = 600
        parameters.blocked_connection_timeout = 300
        return pika.BlockingConnection(parameters)

    @staticmethod
    def _parse_message(body: bytes) -> dict[str, Any]:
        try:
            message = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Message is not valid JSON.") from exc

        if not isinstance(message, dict):
            raise ValueError("Message must be a JSON object.")

        article_key = message.get("article_key")
        if not isinstance(article_key, str) or not article_key.strip():
            raise ValueError("article_key is required.")

        return {"article_key": article_key.strip()}

    @staticmethod
    def _build_embedding_text(article: dict[str, Any]) -> str:
        parts: list[str] = []

        title = (article.get("title") or "").strip()
        summary = (article.get("summary") or "").strip()
        market_impact = (article.get("market_impact") or "").strip()
        key_facts = article.get("key_facts") or []

        if title:
            parts.append(f"Title: {title}")
        if summary:
            parts.append(f"Summary: {summary}")
        if key_facts:
            facts = "\n".join(f"- {str(fact).strip()}" for fact in key_facts if str(fact).strip())
            if facts:
                parts.append(f"Key Facts:\n{facts}")
        if market_impact:
            parts.append(f"Market Impact: {market_impact}")

        text = "\n\n".join(parts).strip()
        if not text:
            raise ValueError("Article has no usable analyzed text for embedding.")

        return text

    def _generate_embedding(self, text: str) -> list[float]:
        response = requests.post(
            self.embedding_service_url,
            json={"texts": [text]},
            timeout=self.embedding_timeout,
        )
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("Embedding service returned invalid JSON.") from exc

        embeddings = payload.get("embeddings") if isinstance(payload, dict) else None
        if not isinstance(embeddings, list) or not embeddings:
            raise ValueError("Embedding service response has no embeddings.")

        vector = embeddings[0]
        if not isinstance(vector, list):
            raise ValueError("Embedding service returned an invalid vector.")

        if len(vector) != self.embedding_dimension:
            raise ValueError(
                "Embedding dimension mismatch: "
                f"expected {self.embedding_dimension}, got {len(vector)}."
            )

        try:
            return [float(value) for value in vector]
        except (TypeError, ValueError) as exc:
            raise ValueError("Embedding vector contains non-numeric values.") from exc

    @staticmethod
    def _safe_ack(channel, delivery_tag) -> bool:
        if channel is None or not channel.is_open:
            print("RabbitMQ channel is closed; message could not be ACKed.")
            return False
        try:
            channel.basic_ack(delivery_tag=delivery_tag)
            print("RabbitMQ message ACKed.")
            return True
        except (pika.exceptions.AMQPError, OSError) as exc:
            print(f"RabbitMQ ACK failed: {exc}")
            return False

    @staticmethod
    def _safe_nack(channel, delivery_tag, *, requeue: bool) -> bool:
        if channel is None or not channel.is_open:
            print("RabbitMQ channel is closed; message could not be NACKed.")
            return False
        try:
            channel.basic_nack(delivery_tag=delivery_tag, requeue=requeue)
            print(f"RabbitMQ message NACKed (requeue={requeue}).")
            return True
        except (pika.exceptions.AMQPError, OSError) as exc:
            print(f"RabbitMQ NACK failed: {exc}")
            return False

    def _on_message(self, channel, method, properties, body: bytes) -> None:
        delivery_tag = method.delivery_tag

        try:
            message = self._parse_message(body)
            article_key = message["article_key"]
        except ValueError as exc:
            print(f"Invalid embedding message: {exc}")
            outcome = self.retry_router.route_failure(
                channel,
                delivery_tag=delivery_tag,
                properties=properties,
                body=body,
                retryable=False,
                error=exc,
            )
            print(f"Invalid message routed to {outcome}.")
            return

        print("=" * 70)
        print(f"Embedding article: {article_key}")

        try:
            article = self.repository.get_embedding_input(article_key)

            if article is None:
                print("Article does not exist in PostgreSQL. ACKing message.")
                self._safe_ack(channel, delivery_tag)
                return

            print(f"Current status: {article['processing_status']}")

            if article["has_embedding"] or article["processing_status"] == "embedded":
                print("Article is already embedded. ACKing duplicate message.")
                self._safe_ack(channel, delivery_tag)
                return

            if article["processing_status"] != "analyzed":
                print(
                    "Article is not in analyzed state; embedding is skipped. "
                    f"Status={article['processing_status']}"
                )
                self._safe_ack(channel, delivery_tag)
                return

            text = self._build_embedding_text(article)
            print(f"Embedding input length: {len(text)}")
            print("Sending article to embedding service...")

            embedding = self._generate_embedding(text)
            print(f"Embedding dimension: {len(embedding)}")

            self.repository.save_embedding(
                article_key=article_key,
                embedding=embedding,
                expected_dimension=self.embedding_dimension,
            )

            print("Embedding saved to PostgreSQL.")
            print("Status: embedded")
            self._safe_ack(channel, delivery_tag)

        except requests.RequestException as exc:
            print(f"Embedding service request failed: {exc}")
            outcome = self.retry_router.route_failure(
                channel,
                delivery_tag=delivery_tag,
                properties=properties,
                body=body,
                retryable=True,
                error=exc,
            )
            print(f"Embedding failure routed to {outcome}.")

        except Exception as exc:
            print(f"Embedding processing failed: {exc}")
            outcome = self.retry_router.route_failure(
                channel,
                delivery_tag=delivery_tag,
                properties=properties,
                body=body,
                retryable=True,
                error=exc,
            )
            print(f"Embedding failure routed to {outcome}.")

        finally:
            print()

    def _register_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame) -> None:
        print(f"Received signal {signum}; stopping embedding worker...")
        self.stop()

    def start(self) -> None:
        print("=" * 70)
        print("Finzer Article Embedding Worker")
        print("=" * 70)
        print(f"Queue: {self.queue_name}")
        print(f"Embedding service: {self.embedding_service_url}")
        print(f"Model: {self.embedding_model}")
        print(f"Dimension: {self.embedding_dimension}")
        print()

        self.connection = self._create_connection()
        self.channel = self.connection.channel()
        QueueTopology(rabbitmq_url=self.rabbitmq_url).declare()
        self.channel.confirm_delivery()
        self.channel.queue_declare(queue=self.queue_name, durable=True)
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=self._on_message,
            auto_ack=False,
        )

        self._register_signal_handlers()
        print("Waiting for embedding messages...")
        print("Press CTRL+C to stop.")
        print()

        try:
            self.channel.start_consuming()
        except KeyboardInterrupt:
            self.stop()
        except pika.exceptions.AMQPError as exc:
            print(f"RabbitMQ consumer connection failed: {exc}")
        finally:
            self.stop()

    def stop(self) -> None:
        if self._stopping:
            return
        self._stopping = True

        print("Stopping article embedding worker...")

        try:
            if self.channel is not None and self.channel.is_open:
                if getattr(self.channel, "is_consuming", False):
                    self.channel.stop_consuming()
        except (pika.exceptions.AMQPError, OSError):
            pass

        try:
            if self.connection is not None and self.connection.is_open:
                self.connection.close()
        except (pika.exceptions.AMQPError, OSError):
            pass

        print("Article embedding worker stopped.")


def main() -> None:
    worker = ArticleEmbeddingWorker()
    worker.start()


if __name__ == "__main__":
    main()
