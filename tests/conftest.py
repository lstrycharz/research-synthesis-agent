"""Shared test fixtures.

Settings read from the OS environment, so every test that builds a Settings object must
be insulated from the host env — otherwise results flip depending on the developer's shell
or a real .env. This autouse fixture strips all settings env vars before each test; tests
that need specific values set them explicitly with monkeypatch.setenv.
"""

import pytest

from src.config import get_settings

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
    for var in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    # get_settings() is lru_cached — clear it so a cached Settings can't leak across tests.
    get_settings.cache_clear()
