# import time
# from typing import Any

# from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

# from app.config.settings import settings


# class BedrockLLMClient:
#     provider = "bedrock"
#     """OpenAI-compatible Amazon Bedrock Chat Completions client."""

#     def __init__(self) -> None:
#         if not settings.BEDROCK_API_KEY:
#             raise ValueError("BEDROCK_API_KEY is not configured.")

#         self.model = settings.BEDROCK_LLM_MODEL
#         self.max_retries = settings.BEDROCK_LLM_MAX_RETRIES
#         self.client = OpenAI(
#             api_key=settings.BEDROCK_API_KEY,
#             base_url=settings.BEDROCK_LLM_BASE_URL,
#             timeout=settings.BEDROCK_LLM_TIMEOUT,
#             max_retries=0,  # Finzer owns the retry policy below.
#         )

#     def chat_completion(
#         self,
#         *,
#         messages: list[dict[str, str]],
#         max_tokens: int,
#         temperature: float,
#     ) -> dict[str, Any]:
#         total_attempts = self.max_retries + 1

#         for attempt in range(1, total_attempts + 1):
#             try:
#                 print(f"Bedrock LLM request attempt {attempt}/{total_attempts}")
#                 response = self.client.chat.completions.create(
#                     model=self.model,
#                     messages=messages,
#                     max_tokens=max_tokens,
#                     temperature=temperature,
#                 )
#                 content = response.choices[0].message.content
#                 if not content:
#                     raise RuntimeError("Bedrock LLM returned empty content.")
#                 return {"choices": [{"message": {"content": content}}]}

#             except (APITimeoutError, APIConnectionError) as exc:
#                 if attempt >= total_attempts:
#                     raise
#                 wait_seconds = 2 ** attempt
#                 print(f"Transient Bedrock LLM failure: {exc}")
#                 print(f"Retrying in {wait_seconds} seconds...")
#                 time.sleep(wait_seconds)

#             except APIStatusError as exc:
#                 # Retry throttling and transient server failures only.
#                 if exc.status_code not in {429, 500, 502, 503, 504} or attempt >= total_attempts:
#                     raise
#                 wait_seconds = 2 ** attempt
#                 print(f"Transient Bedrock HTTP {exc.status_code}: {exc}")
#                 print(f"Retrying in {wait_seconds} seconds...")
#                 time.sleep(wait_seconds)

#         raise RuntimeError("Bedrock LLM request failed unexpectedly.")


import time
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
)

from app.config.settings import settings


class BedrockLLMClient:
    """
    OpenAI-compatible Amazon Bedrock Chat Completions client.

    Responsibilities:
    - Call the Bedrock Mantle OpenAI-compatible endpoint
    - Apply Finzer-owned retry policy
    - Preserve finish_reason so callers can detect truncation
    - Preserve token usage for logging/debugging
    """

    provider = "bedrock"

    def __init__(self) -> None:
        if not settings.BEDROCK_API_KEY:
            raise ValueError(
                "BEDROCK_API_KEY is not configured."
            )

        self.model = settings.BEDROCK_LLM_MODEL
        self.max_retries = settings.BEDROCK_LLM_MAX_RETRIES

        self.client = OpenAI(
            api_key=settings.BEDROCK_API_KEY,
            base_url=settings.BEDROCK_LLM_BASE_URL,
            timeout=settings.BEDROCK_LLM_TIMEOUT,
            # Finzer owns the retry policy below.
            max_retries=0,
        )

    def chat_completion(
        self,
        *,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        """
        Execute one chat completion request.

        Returns a small provider-independent response structure:

        {
            "choices": [
                {
                    "message": {
                        "content": "..."
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": ...,
                "completion_tokens": ...,
                "total_tokens": ...
            }
        }
        """

        total_attempts = self.max_retries + 1

        for attempt in range(1, total_attempts + 1):
            try:
                print(
                    f"Bedrock LLM request attempt "
                    f"{attempt}/{total_attempts}"
                )

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                if not response.choices:
                    raise RuntimeError(
                        "Bedrock LLM returned no choices."
                    )

                choice = response.choices[0]
                content = choice.message.content
                finish_reason = choice.finish_reason

                if not content:
                    raise RuntimeError(
                        "Bedrock LLM returned empty content."
                    )

                usage = None

                if response.usage is not None:
                    usage = {
                        "prompt_tokens": getattr(
                            response.usage,
                            "prompt_tokens",
                            None,
                        ),
                        "completion_tokens": getattr(
                            response.usage,
                            "completion_tokens",
                            None,
                        ),
                        "total_tokens": getattr(
                            response.usage,
                            "total_tokens",
                            None,
                        ),
                    }

                return {
                    "choices": [
                        {
                            "message": {
                                "content": content,
                            },
                            "finish_reason": finish_reason,
                        }
                    ],
                    "usage": usage,
                }

            except (
                APITimeoutError,
                APIConnectionError,
            ) as exc:
                if attempt >= total_attempts:
                    raise

                wait_seconds = 2 ** attempt

                print(
                    f"Transient Bedrock LLM failure: {exc}"
                )
                print(
                    f"Retrying in {wait_seconds} seconds..."
                )

                time.sleep(wait_seconds)

            except APIStatusError as exc:
                # Only retry transient HTTP failures.
                if (
                    exc.status_code
                    not in {
                        429,
                        500,
                        502,
                        503,
                        504,
                    }
                    or attempt >= total_attempts
                ):
                    raise

                wait_seconds = 2 ** attempt

                print(
                    f"Transient Bedrock HTTP "
                    f"{exc.status_code}: {exc}"
                )
                print(
                    f"Retrying in {wait_seconds} seconds..."
                )

                time.sleep(wait_seconds)

        raise RuntimeError(
            "Bedrock LLM request failed unexpectedly."
        )