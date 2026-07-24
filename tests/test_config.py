"""Typed settings loaded from env / .env — no hardcoded secrets.

Env isolation is handled by the autouse fixture in conftest.py, so these tests don't
depend on the host environment or a real .env.
"""

import pytest
from pydantic import ValidationError

from src.config import Settings


def test_settings_applies_model_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "y")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.supervisor_model == "claude-sonnet-5"
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


def test_settings_rejects_zero_max_sub_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    # max_sub_questions=0 would make the graph fan out to nothing and dead-end silently.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "y")
    monkeypatch.setenv("MAX_SUB_QUESTIONS", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
