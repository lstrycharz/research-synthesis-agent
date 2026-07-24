"""Typed application settings, loaded from environment variables / .env.

Secrets are never hardcoded — they come from the environment. Langfuse keys are
optional so the pipeline runs (with local cost tracking only) when they are absent.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required credentials.
    anthropic_api_key: str
    tavily_api_key: str

    # Langfuse — optional. Absent keys => tracing no-ops, cost log still works.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # Model routing and limits (override in .env). Both defaults must stay priced in
    # observability.MODEL_COSTS — main.validate_models fails fast at startup otherwise.
    supervisor_model: str = "claude-sonnet-5"
    worker_model: str = "claude-haiku-4-5-20251001"
    # >= 1: a zero/negative cap would fan the graph out to nothing and dead-end silently.
    max_sub_questions: int = Field(default=5, ge=1)
    search_results_per_query: int = Field(default=5, ge=1)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (reads env / .env once)."""
    # Required fields are populated from the environment, which mypy can't see.
    return Settings()  # type: ignore[call-arg]
