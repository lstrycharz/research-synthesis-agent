"""The summarizer: a Haiku worker that condenses one sub-question's search results.

The deep core `run_summarize` takes an `invoke` callable, so happy/empty paths test with
a fake model and zero cost. Prompt caching and message shape are asserted on build_messages.
"""

from collections.abc import Awaitable, Callable

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.agents.summarizer import build_messages, run_summarize, summarizer_node
from src.state import SearchResult

InvokeFn = Callable[[list[BaseMessage]], Awaitable[AIMessage]]

_HAIKU = "claude-haiku-4-5-20251001"


def _fake_invoke(content: str, *, input_tokens: int, output_tokens: int) -> InvokeFn:
    async def _invoke(messages: list[BaseMessage]) -> AIMessage:
        return AIMessage(
            content=content,
            usage_metadata={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
        )

    return _invoke


def test_build_messages_caches_the_system_prompt() -> None:
    messages = build_messages("What is a battery?", [{"title": "t", "url": "u"}])
    system = messages[0]
    assert isinstance(system, SystemMessage)
    assert isinstance(system.content, list)
    block = system.content[0]
    assert isinstance(block, dict)
    assert block["cache_control"] == {"type": "ephemeral"}


def test_build_messages_includes_sub_question_and_source() -> None:
    messages = build_messages(
        "What is a battery?",
        [{"title": "Batteries 101", "url": "https://ex.com", "content": "info"}],
    )
    human = messages[1]
    assert isinstance(human, HumanMessage)
    text = human.content if isinstance(human.content, str) else str(human.content)
    assert "What is a battery?" in text
    assert "Batteries 101" in text


async def test_run_summarize_happy_path_builds_summary_and_cost() -> None:
    sr: SearchResult = {
        "sub_question": "What is a battery?",
        "results": [{"title": "t", "url": "u", "content": "c"}],
        "node_id": "searcher_0",
    }
    invoke = _fake_invoke("Batteries store energy.", input_tokens=1000, output_tokens=500)
    summary, entry = await run_summarize(sr, model_name=_HAIKU, invoke=invoke)

    assert summary["content"] == "Batteries store energy."
    assert summary["tokens_used"] == 1500
    assert summary["model"] == _HAIKU
    assert round(summary["cost_usd"], 6) == 0.0035  # (1000*$1 + 500*$5) / 1e6
    assert entry is not None
    assert entry["node"] == "summarizer"
    assert round(entry["cost_usd"], 6) == 0.0035


async def test_run_summarize_empty_results_skips_the_llm() -> None:
    calls = {"n": 0}

    async def counting_invoke(messages: list[BaseMessage]) -> AIMessage:
        calls["n"] += 1
        return AIMessage(content="should not run")

    sr: SearchResult = {"sub_question": "q", "results": [], "node_id": "searcher_0"}
    summary, entry = await run_summarize(sr, model_name=_HAIKU, invoke=counting_invoke)

    assert calls["n"] == 0  # no LLM call for empty results
    assert entry is None  # so no cost entry
    assert summary["cost_usd"] == 0.0
    assert summary["tokens_used"] == 0
    assert summary["content"]  # a non-empty "no results" note


async def test_run_summarize_model_error_returns_degraded_summary() -> None:
    # A model failure (e.g. 429 after retries) must degrade, not kill sibling branches.
    async def boom(messages: list[BaseMessage]) -> AIMessage:
        raise RuntimeError("api exploded")

    sr: SearchResult = {
        "sub_question": "q",
        "results": [{"title": "t"}],
        "node_id": "searcher_0",
    }
    summary, entry = await run_summarize(sr, model_name=_HAIKU, invoke=boom)
    assert entry is None  # no cost entry for a failed call
    assert summary["cost_usd"] == 0.0
    assert summary["tokens_used"] == 0
    assert "api exploded" in summary["content"]


async def test_run_summarize_missing_usage_records_zero_cost() -> None:
    # A successful call with no usage_metadata records a $0 entry (and warns).
    async def no_usage(messages: list[BaseMessage]) -> AIMessage:
        return AIMessage(content="a summary with no usage info")

    sr: SearchResult = {
        "sub_question": "q",
        "results": [{"title": "t"}],
        "node_id": "searcher_0",
    }
    summary, entry = await run_summarize(sr, model_name=_HAIKU, invoke=no_usage)
    assert summary["tokens_used"] == 0
    assert entry is not None
    assert entry["input_tokens"] == 0
    assert entry["cost_usd"] == 0.0


async def test_run_summarize_empty_results_note_mentions_search_error() -> None:
    sr: SearchResult = {
        "sub_question": "q",
        "results": [],
        "node_id": "searcher_0",
        "error": "Tavily timeout",
    }
    invoke = _fake_invoke("unused", input_tokens=0, output_tokens=0)
    summary, _ = await run_summarize(sr, model_name=_HAIKU, invoke=invoke)
    assert "Tavily timeout" in summary["content"]


async def test_summarizer_node_returns_summaries_and_cost_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "y")

    async def stub(
        search_result: SearchResult, *, model_name: str, invoke: InvokeFn
    ) -> tuple[dict[str, object], dict[str, object]]:
        summary = {
            "sub_question": search_result["sub_question"],
            "content": "c",
            "tokens_used": 10,
            "model": model_name,
            "cost_usd": 0.001,
        }
        entry = {
            "node": "summarizer",
            "model": model_name,
            "input_tokens": 5,
            "output_tokens": 5,
            "cost_usd": 0.001,
            "latency_ms": 100,
        }
        return summary, entry

    monkeypatch.setattr("src.agents.summarizer.run_summarize", stub)
    update = await summarizer_node(
        {"sub_question": "q", "results": [{"title": "t"}], "node_id": "searcher_0"}
    )

    assert isinstance(update["summaries"], list)
    assert isinstance(update["cost_log"], list)
    assert update["summaries"][0]["content"] == "c"


async def test_summarizer_node_omits_cost_log_when_no_llm_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "y")

    async def stub(
        search_result: SearchResult, *, model_name: str, invoke: InvokeFn
    ) -> tuple[dict[str, object], None]:
        summary = {
            "sub_question": search_result["sub_question"],
            "content": "no results",
            "tokens_used": 0,
            "model": model_name,
            "cost_usd": 0.0,
        }
        return summary, None

    monkeypatch.setattr("src.agents.summarizer.run_summarize", stub)
    update = await summarizer_node({"sub_question": "q", "results": [], "node_id": "searcher_0"})

    assert isinstance(update["summaries"], list)
    assert "cost_log" not in update
