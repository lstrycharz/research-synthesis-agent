"""The searcher: a no-LLM Tavily worker that must never crash the graph.

The deep core `run_tavily_search` takes a search *callable*, so every path — happy,
empty, retryable-then-success, retry-exhausted, non-retryable — is tested with fakes and
zero network. `searcher_node` is tested by stubbing the core.
"""

from collections.abc import Awaitable, Callable

import httpx
import pytest
from tavily.errors import InvalidAPIKeyError, UsageLimitExceededError
from tavily.errors import TimeoutError as TavilyTimeoutError

from src.agents.searcher import run_tavily_search, searcher_node

SearchFn = Callable[[str], Awaitable[dict[str, object]]]


def _returns(payload: dict[str, object]) -> SearchFn:
    async def _search(query: str) -> dict[str, object]:
        return payload

    return _search


async def test_run_tavily_search_happy_path_returns_results() -> None:
    search = _returns({"results": [{"title": "Batteries 101", "url": "https://example.com"}]})
    results, error = await run_tavily_search("What is a battery?", search=search)
    assert error is None
    assert results == [{"title": "Batteries 101", "url": "https://example.com"}]


async def test_run_tavily_search_empty_results_sets_error() -> None:
    results, error = await run_tavily_search("obscure query", search=_returns({"results": []}))
    assert results == []
    assert error is not None


async def test_run_tavily_search_missing_results_key_sets_error() -> None:
    results, error = await run_tavily_search("q", search=_returns({}))
    assert results == []
    assert error is not None


def _http_status_error(status: int) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError(
        f"http {status}",
        request=httpx.Request("POST", "https://api.tavily.com/search"),
        response=httpx.Response(status),
    )


async def test_run_tavily_search_retries_once_on_429_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.agents.searcher._RETRY_BACKOFF_S", 0.0)
    calls = {"n": 0}

    async def flaky(query: str) -> dict[str, object]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise UsageLimitExceededError("rate limited")
        return {"results": [{"title": "ok"}]}

    results, error = await run_tavily_search("q", search=flaky)
    assert calls["n"] == 2  # retried exactly once
    assert error is None
    assert results == [{"title": "ok"}]


async def test_run_tavily_search_retry_exhausted_on_5xx_sets_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.agents.searcher._RETRY_BACKOFF_S", 0.0)
    calls = {"n": 0}

    async def always_500(query: str) -> dict[str, object]:
        calls["n"] += 1
        raise _http_status_error(503)

    results, error = await run_tavily_search("q", search=always_500)
    assert calls["n"] == 2  # initial + one retry, then gives up
    assert results == []
    assert error is not None


async def test_run_tavily_search_does_not_retry_on_bad_key() -> None:
    calls = {"n": 0}

    async def bad_key(query: str) -> dict[str, object]:
        calls["n"] += 1
        raise InvalidAPIKeyError("nope")

    results, error = await run_tavily_search("q", search=bad_key)
    assert calls["n"] == 1  # non-retryable: called exactly once
    assert results == []
    assert error is not None


async def test_run_tavily_search_does_not_retry_on_timeout() -> None:
    # Tavily converts an httpx timeout into its own TimeoutError — a 10s cap is a spec
    # requirement, and a timeout must become an error (not a retry).
    calls = {"n": 0}

    async def times_out(query: str) -> dict[str, object]:
        calls["n"] += 1
        raise TavilyTimeoutError(10.0)

    results, error = await run_tavily_search("q", search=times_out)
    assert calls["n"] == 1  # non-retryable
    assert results == []
    assert error is not None


async def test_run_tavily_search_does_not_retry_on_4xx_status() -> None:
    # Pins the >= 500 boundary in _is_retryable: a 404 must not be retried.
    calls = {"n": 0}

    async def not_found(query: str) -> dict[str, object]:
        calls["n"] += 1
        raise _http_status_error(404)

    results, error = await run_tavily_search("q", search=not_found)
    assert calls["n"] == 1
    assert results == []
    assert error is not None


async def test_searcher_node_records_error_and_node_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "y")

    async def stub_core(sub_question: str, *, search: SearchFn) -> tuple[list, str | None]:
        return [], "boom"

    monkeypatch.setattr("src.agents.searcher.run_tavily_search", stub_core)
    update = await searcher_node({"sub_question": "Q1", "index": 2})

    results = update["search_results"]
    assert isinstance(results, list)
    result = results[0]
    assert result["node_id"] == "searcher_2"
    assert result["error"] == "boom"
    assert result["results"] == []


async def test_searcher_node_omits_error_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "y")

    async def stub_core(sub_question: str, *, search: SearchFn) -> tuple[list, str | None]:
        return [{"title": "ok"}], None

    monkeypatch.setattr("src.agents.searcher.run_tavily_search", stub_core)
    update = await searcher_node({"sub_question": "Q1", "index": 0})

    results = update["search_results"]
    assert isinstance(results, list)
    assert "error" not in results[0]
