"""Typed settings loaded from env / .env — no hardcoded secrets.

These tests must be hermetic: they disable the .env file source (_env_file=None) and
clear any ambient settings env vars, so results don't flip once a real .env exists.
"""

import pytest
from pydantic import ValidationError

from src.config import Settings

_SETTINGS_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "TAVILY_API_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_HOST",
    "SUPERVISOR_MODEL",
    "WORKER_MODEL",
    "MAX_SUB_QUESTIONS",
    "SEARCH_RESULTS_PER_QUERY",
)


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip ambient settings env vars so tests don't depend on the host environment."""
    for var in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_settings_applies_model_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "y")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.supervisor_model == "claude-sonnet-4-6"
    assert settings.worker_model == "claude-haiku-4-5-20251001"
    assert settings.max_sub_questions == 5


def test_settings_langfuse_keys_default_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # Langfuse-optional: the app must run without these set.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "y")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.langfuse_public_key is None
    assert settings.langfuse_secret_key is None


def test_settings_requires_anthropic_key() -> None:
    # Env is cleared by the autouse fixture; no .env source -> required keys missing.
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
