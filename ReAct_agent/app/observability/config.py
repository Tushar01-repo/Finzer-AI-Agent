
"""Central configuration for Finzer agent observability."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ObservabilitySettings(BaseSettings):
    """Environment-driven settings for logging, tracing and metrics."""

    model_config = SettingsConfigDict(
        env_prefix="FINZER_OBS_",
        env_file="local.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "finzer-react-agent"
    environment: Literal["development", "testing", "staging", "production"] = (
        "development"
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = (
        "INFO"
    )
    log_format: Literal["json", "console"] = "json"

    tracing_enabled: bool = True
    tracing_backend: Literal["none", "langsmith", "opentelemetry"] = "none"
    tracing_sample_rate: float = Field(default=1.0, ge=0.0, le=1.0)

    metrics_enabled: bool = True
    capture_token_usage: bool = True
    capture_cost_estimates: bool = True

    redact_sensitive_data: bool = True
    log_tool_arguments: bool = False
    log_model_prompts: bool = False
    log_model_responses: bool = False

    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("service_name cannot be empty")
        return value

    @field_validator("tracing_backend")
    @classmethod
    def validate_tracing_backend(cls, value: str) -> str:
        return value.lower()


@lru_cache(maxsize=1)
def get_observability_settings() -> ObservabilitySettings:
    """Return cached settings for the current process."""
    return ObservabilitySettings()


def reset_observability_settings() -> None:
    """Clear cached settings, primarily for tests."""
    get_observability_settings.cache_clear()
