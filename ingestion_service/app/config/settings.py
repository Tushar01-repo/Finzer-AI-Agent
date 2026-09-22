import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = Path(os.getenv("FINZER_ENV_FILE", PROJECT_ROOT / "local.env"))
if ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=False)
else:
    load_dotenv(override=False)


def _as_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


class Settings:
    APP_NAME = os.getenv("APP_NAME", "finzer-ingestion-service")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "local")

    NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY", "")
    NEWSDATA_BASE_URL = os.getenv("NEWSDATA_BASE_URL", "https://newsdata.io/api/1/latest")
    MAX_PAGES_PER_FEED = int(os.getenv("MAX_PAGES_PER_FEED", "3"))

    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))
    ARTICLE_TIMEOUT = int(os.getenv("ARTICLE_TIMEOUT", "20"))
    REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "1.0"))
    MAX_ARTICLES_PER_FEED = int(os.getenv("MAX_ARTICLES_PER_FEED", "20"))

    DATABASE_URL = os.getenv("DATABASE_URL", "")

    RABBITMQ_URL = os.getenv("RABBITMQ_URL", "")
    ARTICLE_QUEUE = os.getenv("ARTICLE_QUEUE", "article.processing")
    ARTICLE_RETRY_QUEUE = os.getenv("ARTICLE_RETRY_QUEUE", "article.processing.retry")
    ARTICLE_DLQ = os.getenv("ARTICLE_DLQ", "article.processing.dlq")
    ARTICLE_RETRY_DELAYS_MS = tuple(
        int(value.strip())
        for value in os.getenv("ARTICLE_RETRY_DELAYS_MS", "30000,120000,600000").split(",")
        if value.strip()
    )
    ARTICLE_EMBEDDING_QUEUE = os.getenv("ARTICLE_EMBEDDING_QUEUE", "article.embedding")
    ARTICLE_EMBEDDING_RETRY_QUEUE = os.getenv("ARTICLE_EMBEDDING_RETRY_QUEUE", "article.embedding.retry")
    ARTICLE_EMBEDDING_DLQ = os.getenv("ARTICLE_EMBEDDING_DLQ", "article.embedding.dlq")

    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    BEDROCK_API_KEY = os.getenv("BEDROCK_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

    GENERATOR_PROVIDER = os.getenv("GENERATOR_PROVIDER", "auto").strip().lower()
    GENERATOR_PRIMARY = os.getenv("GENERATOR_PRIMARY", "bedrock").strip().lower()
    GENERATOR_FALLBACK = os.getenv("GENERATOR_FALLBACK", "openai").strip().lower()
    OPENAI_LLM_MODEL = os.getenv("OPENAI_LLM_MODEL", "gpt-5.6-luna")
    OPENAI_LLM_TIMEOUT = float(os.getenv("OPENAI_LLM_TIMEOUT", "120"))
    OPENAI_LLM_MAX_RETRIES = int(os.getenv("OPENAI_LLM_MAX_RETRIES", "2"))

    BEDROCK_LLM_BASE_URL = os.getenv(
        "BEDROCK_LLM_BASE_URL",
        "https://bedrock-mantle.us-east-1.api.aws/v1",
    )
    BEDROCK_LLM_MODEL = os.getenv("BEDROCK_LLM_MODEL", "openai.gpt-oss-120b")
    BEDROCK_LLM_TIMEOUT = float(os.getenv("BEDROCK_LLM_TIMEOUT", "300"))
    BEDROCK_LLM_MAX_RETRIES = int(os.getenv("BEDROCK_LLM_MAX_RETRIES", "2"))
    BEDROCK_LLM_MAX_TOKENS = int(os.getenv("BEDROCK_LLM_MAX_TOKENS", "1000"))
    BEDROCK_LLM_TEMPERATURE = float(os.getenv("BEDROCK_LLM_TEMPERATURE", "0.0"))
    LLM_MAX_ARTICLE_CHARS = int(os.getenv("LLM_MAX_ARTICLE_CHARS", "18000"))
    ARTICLE_RELEVANCE_THRESHOLD = float(os.getenv("ARTICLE_RELEVANCE_THRESHOLD", "0.6"))

    EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "auto").strip().lower()
    EMBEDDING_PRIMARY = os.getenv("EMBEDDING_PRIMARY", "bedrock").strip().lower()
    EMBEDDING_FALLBACK = os.getenv("EMBEDDING_FALLBACK", "openai").strip().lower()
    OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    BEDROCK_EMBEDDING_MODEL = os.getenv(
        "BEDROCK_EMBEDDING_MODEL",
        "amazon.titan-embed-text-v2:0",
    )
    EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
    EMBEDDING_NORMALIZE = _as_bool("EMBEDDING_NORMALIZE", True)
    EMBEDDING_REQUEST_TIMEOUT = int(os.getenv("EMBEDDING_REQUEST_TIMEOUT", "60"))


settings = Settings()
