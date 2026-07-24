"""Summarizer node: condense one sub-question's search results into a short section.

Model: Haiku (worker). The static system prompt carries a ``cache_control: ephemeral``
marker to wire prompt caching, but it is currently INERT: the prompt (~80 tokens) is far
below Haiku's 2048-token minimum cacheable prefix, so Anthropic processes it uncached. The
marker only becomes effective if the system prompt grows past that threshold. Every real LLM
call routes its tokens through ``observability.log_llm_call`` for cost tracking, and is
traced by the Langfuse CallbackHandler when Langfuse is configured.

Empty search results skip the LLM entirely: an empty/failed search yields a free, canned
"no sources" note (cost 0, no CostEntry). A model failure degrades the same way (error note,
cost 0, no CostEntry) so one failed branch never kills its siblings in the fan-out.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import SecretStr

from src.config import get_settings
from src.observability import get_langfuse_client, log_llm_call
from src.state import CostEntry, SearchResult, Summary

logger = logging.getLogger(__name__)

# A callable that runs the model on the built messages. Injected for testability.
InvokeFn = Callable[[list[BaseMessage]], Awaitable[AIMessage]]

_MAX_TOKENS = 512

# Static instructions — identical on every call, so it caches. Keep this frozen.
SYSTEM_PROMPT = (
    "You are a research summarizer. Given a sub-question and raw web search results, "
    "write a single cohesive summary of 150-250 words that answers the sub-question using "
    "only the provided results. State key facts plainly and attribute claims to their source "
    "titles. If the results are thin or conflicting, add a short confidence note. Do not invent "
    "facts beyond the results, and do not include a preamble — output only the summary."
)


def _format_results(results: list[dict[str, object]]) -> str:
    """Render Tavily results as a readable, numbered source list for the prompt."""
    lines: list[str] = []
    for i, result in enumerate(results, start=1):
        title = result.get("title", "(untitled)")
        url = result.get("url", "")
        content = result.get("content", "")
        lines.append(f"[{i}] {title} ({url})\n{content}")
    return "\n\n".join(lines)


def build_messages(sub_question: str, results: list[dict[str, object]]) -> list[BaseMessage]:
    """Build the [cached system, human] message pair for the summarizer call."""
    # cache_control wires prompt caching, but is a no-op today: this prompt is well under
    # Haiku's 2048-token minimum cacheable prefix, so nothing is actually cached.
    system = SystemMessage(
        content=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    )
    human = HumanMessage(
        content=(
            f"Sub-question: {sub_question}\n\n"
            f"Search results:\n{_format_results(results)}\n\n"
            "Write the summary."
        )
    )
    return [system, human]


async def run_summarize(
    search_result: SearchResult,
    *,
    model_name: str,
    invoke: InvokeFn,
) -> tuple[Summary, CostEntry | None]:
    """Summarize one SearchResult. Returns (Summary, CostEntry|None).

    Empty/failed searches skip the LLM and return a canned note with no CostEntry.
    """
    sub_question = search_result["sub_question"]
    results = search_result.get("results", [])

    if not results:
        note = (
            f"No search results were available for {sub_question!r}; "
            "unable to summarize (low confidence)."
        )
        error = search_result.get("error")
        if error:
            note += f" Search error: {error}"
        summary: Summary = {
            "sub_question": sub_question,
            "content": note,
            "tokens_used": 0,
            "model": model_name,
            "cost_usd": 0.0,
        }
        return summary, None

    start = time.perf_counter()
    try:
        response = await invoke(build_messages(sub_question, results))
    except Exception as exc:  # noqa: BLE001 - one failed branch must not kill the fan-out
        logger.warning("summarizer: model call failed for %r: %s", sub_question, exc)
        degraded: Summary = {
            "sub_question": sub_question,
            "content": f"Failed to summarize {sub_question!r} (search succeeded): {exc}",
            "tokens_used": 0,
            "model": model_name,
            "cost_usd": 0.0,
        }
        return degraded, None
    latency_ms = int((time.perf_counter() - start) * 1000)

    content = response.content if isinstance(response.content, str) else str(response.content)
    usage = response.usage_metadata
    if usage is None:
        logger.warning("summarizer: response missing usage_metadata; cost recorded as 0")
    input_tokens = usage["input_tokens"] if usage else 0
    output_tokens = usage["output_tokens"] if usage else 0

    entry = log_llm_call(
        node="summarizer",
        model=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )
    summary = {
        "sub_question": sub_question,
        "content": content,
        "tokens_used": input_tokens + output_tokens,
        "model": model_name,
        "cost_usd": entry["cost_usd"],
    }
    return summary, entry


async def summarizer_node(payload: dict[str, object]) -> dict[str, object]:
    """LangGraph node: summarize one SearchResult, return a partial state update."""
    settings = get_settings()
    search_result = cast(SearchResult, payload)

    from langchain_anthropic import ChatAnthropic

    # `model` / `max_tokens` are pydantic aliases mypy can't see; api_key wants SecretStr.
    model = ChatAnthropic(  # type: ignore[call-arg]
        model=settings.worker_model,
        api_key=SecretStr(settings.anthropic_api_key),  # explicit — env-reading unreliable here
        max_tokens=_MAX_TOKENS,
    )

    config: RunnableConfig = {}
    # Constructing the Langfuse client registers it in the global registry that
    # CallbackHandler() resolves — the return value's side effect is load-bearing.
    if get_langfuse_client(settings) is not None:
        from langfuse.langchain import CallbackHandler

        config = {"callbacks": [CallbackHandler()]}

    async def _invoke(messages: list[BaseMessage]) -> AIMessage:
        response = await model.ainvoke(messages, config=config)
        return cast(AIMessage, response)

    summary, entry = await run_summarize(
        search_result, model_name=settings.worker_model, invoke=_invoke
    )

    update: dict[str, object] = {"summaries": [summary]}
    if entry is not None:
        update["cost_log"] = [entry]
    return update
