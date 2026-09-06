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
    # Google News
    # ------------------------------------------------------------------

    GOOGLE_NEWS_BASE_URL = os.getenv(
        "GOOGLE_NEWS_BASE_URL",
        "https://news.google.com/rss/search"
    )

    GOOGLE_NEWS_LANGUAGE = os.getenv(
        "GOOGLE_NEWS_LANGUAGE",
        "en-IN"
    )

    GOOGLE_NEWS_COUNTRY = os.getenv(
        "GOOGLE_NEWS_COUNTRY",
        "IN"
    )

    GOOGLE_NEWS_CEID = os.getenv(
        "GOOGLE_NEWS_CEID",
        "IN:en"
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


settings = Settings()