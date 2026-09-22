import time
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from app.config.settings import settings


class OpenAILLMClient:
    """OpenAI Chat Completions fallback for Finzer article analysis."""

    provider = "openai"

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not configured.")
        self.model = settings.OPENAI_LLM_MODEL
        self.max_retries = settings.OPENAI_LLM_MAX_RETRIES
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=settings.OPENAI_LLM_TIMEOUT,
            max_retries=0,
        )

    def chat_completion(self, *, messages: list[dict[str, str]], max_tokens: int, temperature: float) -> dict[str, Any]:
        total_attempts = self.max_retries + 1
        for attempt in range(1, total_attempts + 1):
            try:
                print(f"OpenAI LLM request attempt {attempt}/{total_attempts}")
                response = self.client.chat.completions.create(
                    model=self.model, messages=messages, max_completion_tokens=max_tokens
                )
                content = response.choices[0].message.content
                if not content:
                    raise RuntimeError("OpenAI LLM returned empty content.")
                return {"choices": [{"message": {"content": content}}]}
            except (APITimeoutError, APIConnectionError) as exc:
                if attempt >= total_attempts:
                    raise
                wait_seconds = 2 ** attempt
                print(f"Transient OpenAI LLM failure: {exc}; retrying in {wait_seconds}s")
                time.sleep(wait_seconds)
            except APIStatusError as exc:
                if exc.status_code not in {408, 409, 429, 500, 502, 503, 504} or attempt >= total_attempts:
                    raise
                wait_seconds = 2 ** attempt
                print(f"Transient OpenAI HTTP {exc.status_code}; retrying in {wait_seconds}s")
                time.sleep(wait_seconds)
        raise RuntimeError("OpenAI LLM request failed unexpectedly.")
