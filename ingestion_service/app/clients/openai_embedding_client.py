from openai import OpenAI

from app.config.settings import settings


class OpenAIEmbeddingClient:
    """OpenAI embedding provider using the shared Finzer vector dimension."""

    provider = "openai"

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not configured.")
        self.model = settings.OPENAI_EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=settings.EMBEDDING_REQUEST_TIMEOUT)

    def embed(self, text: str) -> list[float]:
        text=text.strip()
        if not text:
            raise ValueError("Embedding input cannot be empty.")
        response=self.client.embeddings.create(model=self.model, input=text, dimensions=self.dimension)
        vector=response.data[0].embedding
        if len(vector) != self.dimension:
            raise ValueError(f"Embedding dimension mismatch: expected {self.dimension}, got {len(vector)}.")
        return [float(value) for value in vector]
