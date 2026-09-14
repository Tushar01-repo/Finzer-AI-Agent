import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    APP_NAME = os.getenv(
        "APP_NAME",
        "finzer-ingestion-service"
    )

    ENVIRONMENT = os.getenv(
        "ENVIRONMENT",
        "development"
    )

    # ------------------------------------------------------------------
    # NewsData IO
    # ------------------------------------------------------------------

    NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY", "")
    NEWSDATA_BASE_URL = os.getenv(
        "NEWSDATA_BASE_URL",
        "https://newsdata.io/api/1/latest",
    )
    MAX_PAGES_PER_FEED = int(
        os.getenv("MAX_PAGES_PER_FEED", "3")
    )

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    REQUEST_TIMEOUT = int(
        os.getenv("REQUEST_TIMEOUT", "15")
    )

    ARTICLE_TIMEOUT = int(
        os.getenv("ARTICLE_TIMEOUT", "20")
    )

    REQUEST_DELAY_SECONDS = float(
        os.getenv("REQUEST_DELAY_SECONDS", "1.0")
    )

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    MAX_ARTICLES_PER_FEED = int(
        os.getenv("MAX_ARTICLES_PER_FEED", "20")
    )

    # ------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------

    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        ""
    )

    # ------------------------------------------------------------------
    # RabbitMQ
    # ------------------------------------------------------------------

    RABBITMQ_URL = os.getenv(
        "RABBITMQ_URL",
        ""
    )

    ARTICLE_QUEUE = os.getenv(
        "ARTICLE_QUEUE",
        "article.processing"
    )

    ARTICLE_RETRY_QUEUE = os.getenv(
        "ARTICLE_RETRY_QUEUE",
        "article.processing.retry"
    )

    ARTICLE_DLQ = os.getenv(
        "ARTICLE_DLQ",
        "article.processing.dlq"
    )

    ARTICLE_RETRY_DELAYS_MS = tuple(
        int(value.strip())
        for value in os.getenv(
            "ARTICLE_RETRY_DELAYS_MS",
            "30000,120000,600000",
        ).split(",")
        if value.strip()
    )

    ARTICLE_EMBEDDING_QUEUE = os.getenv(
        "ARTICLE_EMBEDDING_QUEUE",
        "article.embedding"
    )

    ARTICLE_EMBEDDING_RETRY_QUEUE = os.getenv(
        "ARTICLE_EMBEDDING_RETRY_QUEUE",
        "article.embedding.retry"
    )

    ARTICLE_EMBEDDING_DLQ = os.getenv(
        "ARTICLE_EMBEDDING_DLQ",
        "article.embedding.dlq"
    )


    # ------------------------------------------------------------------
    # Embedding service
    # ------------------------------------------------------------------

    EMBEDDING_SERVICE_URL = os.getenv(
        "EMBEDDING_SERVICE_URL",
        ""
    )

    EMBEDDING_REQUEST_TIMEOUT = int(
        os.getenv("EMBEDDING_REQUEST_TIMEOUT", "60")
    )

    EMBEDDING_MODEL = os.getenv(
        "EMBEDDING_MODEL",
        "sentence-transformers/all-MiniLM-L6-v2"
    )

    EMBEDDING_DIMENSION = int(
        os.getenv("EMBEDDING_DIMENSION", "384")
    )


settings = Settings()
