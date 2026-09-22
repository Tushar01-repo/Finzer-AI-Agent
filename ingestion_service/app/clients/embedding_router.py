from app.clients.bedrock_embedding_client import BedrockEmbeddingClient
from app.clients.openai_embedding_client import OpenAIEmbeddingClient
from app.config.settings import settings


class EmbeddingRouter:
    """Select one healthy embedding provider and lock it for this worker session.

    Embedding providers are never switched article-by-article because vectors from
    different models are not comparable even when they have the same dimension.
    """

    PROBE_TEXT = "Finzer embedding provider health check."

    def __init__(self) -> None:
        self.client = None
        self.provider = None
        self.model = None
        self.dimension = settings.EMBEDDING_DIMENSION
        self._select_provider()

    def _order(self) -> list[str]:
        if settings.EMBEDDING_PROVIDER != "auto":
            return [settings.EMBEDDING_PROVIDER]
        order=[]
        for name in (settings.EMBEDDING_PRIMARY, settings.EMBEDDING_FALLBACK):
            if name not in order:
                order.append(name)
        return order

    @staticmethod
    def _build(name: str):
        if name == "bedrock":
            return BedrockEmbeddingClient()
        if name == "openai":
            return OpenAIEmbeddingClient()
        raise ValueError(f"Unsupported embedding provider: {name}")

    def _select_provider(self) -> None:
        errors=[]
        for name in self._order():
            try:
                print(f"Checking embedding provider: {name}...")
                candidate=self._build(name)
                candidate.embed(self.PROBE_TEXT)
                self.client=candidate
                self.provider=name
                self.model=candidate.model
                print(f"Embedding provider selected and locked: {name} ({self.model})")
                return
            except Exception as exc:
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
                print(f"Embedding provider {name} unavailable: {type(exc).__name__}: {exc}")
        raise RuntimeError("No embedding provider is available: " + " | ".join(errors))

    def embed(self, text: str) -> list[float]:
        return self.client.embed(text)
