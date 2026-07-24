"""Searcher node: fetch Tavily results for one sub-question. No LLM.

Contract: given valid config and a well-formed payload, this node MUST NOT raise on a
runtime/network failure — timeout, rate limit, server error, bad API key, or empty results
are all captured in the returned SearchResult's ``error`` field so the summarizer can handle
them and the pipeline continues. Transient failures (429 rate limit, 5xx server errors) are
retried once with a short backoff; permanent failures (bad key, bad request) are not.

Config/payload errors DO fail fast on purpose: a missing TAVILY_API_KEY or a malformed
Send payload is a startup/programming error, not something to bury in N error-results.
main.py validates settings before invoking the graph so config errors surface at startup.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import cast

import httpx
from tavily import AsyncTavilyClient
from tavily.errors import UsageLimitExceededError

from src.config import get_settings
from src.state import SearchResult

_TIMEOUT_S = 10.0
_RETRY_BACKOFF_S = 0.5

# A search callable: sub-question -> raw Tavily response dict. Injected for testability.
SearchFn = Callable[[str], Awaitable[dict[str, object]]]


def _is_retryable(exc: Exception) -> bool:
    """Transient failures worth one retry: 429 rate limit or a 5xx server error."""
    if isinstance(exc, UsageLimitExceededError):  # Tavily maps HTTP 429 to this
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


async def run_tavily_search(
    sub_question: str,
    *,
    search: SearchFn,
) -> tuple[list[dict[str, object]], str | None]:
    """Search for one sub-question. Returns (results, error); never raises.

    ``error`` is None on success, otherwise a short human-readable reason.
    """
    last_error = "Tavily search failed"
    for attempt in range(2):  # initial attempt + at most one retry
        try:
            response = await search(sub_question)
        except Exception as exc:  # noqa: BLE001 - node must never crash the graph
            last_error = f"Tavily error for {sub_question!r}: {exc}"
            if _is_retryable(exc) and attempt == 0:
                await asyncio.sleep(_RETRY_BACKOFF_S)
                continue
            return [], last_error

        raw = response.get("results")
        results = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
        if not results:
            return [], f"No results for {sub_question!r}"
        return results, None

    return [], last_error  # unreachable (attempt 1 always returns); satisfies mypy


async def searcher_node(payload: dict[str, object]) -> dict[str, object]:
    """LangGraph node: search one sub-question, return a partial state update.

    ``payload`` carries ``sub_question`` and an ``index`` (for the node id). Returns
    ``{"search_results": [SearchResult]}`` which the graph's reducer appends.
    """
    settings = get_settings()
    sub_question = str(payload["sub_question"])
    index = payload.get("index", 0)  # only used to build the node id

    async with httpx.AsyncClient(timeout=_TIMEOUT_S) as http_client:
        tavily = AsyncTavilyClient(api_key=settings.tavily_api_key, client=http_client)

        async def _search(query: str) -> dict[str, object]:
            response = await tavily.search(
                query,
                max_results=settings.search_results_per_query,
                timeout=_TIMEOUT_S,
            )
            return cast(dict[str, object], response)

        results, error = await run_tavily_search(sub_question, search=_search)

    result: SearchResult = {
        "sub_question": sub_question,
        "results": results,
        "node_id": f"searcher_{index}",
    }
    if error is not None:
        result["error"] = error
    return {"search_results": [result]}
