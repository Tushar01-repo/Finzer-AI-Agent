from typing import Any

from app.clients.bedrock_llm_client import BedrockLLMClient
from app.clients.openai_llm_client import OpenAILLMClient
from app.config.settings import settings


class LLMRouter:
    """Route generation independently from embeddings, with per-request fallback."""

    def __init__(self) -> None:
        self.clients = {}
        for name, factory in (("bedrock", BedrockLLMClient), ("openai", OpenAILLMClient)):
            try:
                self.clients[name] = factory()
            except Exception as exc:
                print(f"Generator provider {name} is not configured: {exc}")
        self.order = self._provider_order()
        if not self.order:
            raise RuntimeError("No generator provider is configured.")

    def _provider_order(self) -> list[str]:
        if settings.GENERATOR_PROVIDER != "auto":
            return [settings.GENERATOR_PROVIDER] if settings.GENERATOR_PROVIDER in self.clients else []
        order=[]
        for name in (settings.GENERATOR_PRIMARY, settings.GENERATOR_FALLBACK):
            if name in self.clients and name not in order:
                order.append(name)
        return order

    @property
    def model(self) -> str:
        return self.clients[self.order[0]].model

    def chat_completion(self, *, messages: list[dict[str, str]], max_tokens: int, temperature: float) -> dict[str, Any]:
        errors=[]
        for index, name in enumerate(self.order):
            client=self.clients[name]
            try:
                print(f"Generator route: {name} ({client.model})")
                return client.chat_completion(messages=messages, max_tokens=max_tokens, temperature=temperature)
            except Exception as exc:
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
                if index + 1 < len(self.order):
                    print(f"Generator provider {name} failed; falling back to {self.order[index+1]}.")
        raise RuntimeError("All generator providers failed: " + " | ".join(errors))
