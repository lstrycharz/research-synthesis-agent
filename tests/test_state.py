"""The shared 'clipboard' schemas the graph passes between nodes.

TypedDicts don't validate at runtime on their own, so we drive them through
pydantic's TypeAdapter to assert they accept correct shapes and reject wrong ones.
"""

import pytest
from pydantic import TypeAdapter, ValidationError

from src.state import CostEntry, ResearchState, SearchResult, Summary


def test_cost_entry_accepts_valid_types() -> None:
    entry: CostEntry = {
        "node": "summarizer",
        "model": "claude-haiku-4-5-20251001",
        "input_tokens": 100,
        "output_tokens": 50,
        "cost_usd": 0.0004,
        "latency_ms": 1200,
    }
    assert TypeAdapter(CostEntry).validate_python(entry) == entry


def test_cost_entry_rejects_non_numeric_cost() -> None:
    bad = {
        "node": "summarizer",
        "model": "claude-haiku-4-5-20251001",
        "input_tokens": 100,
        "output_tokens": 50,
        "cost_usd": "free",  # wrong type: str where float expected
        "latency_ms": 1200,
    }
    with pytest.raises(ValidationError):
        TypeAdapter(CostEntry).validate_python(bad)


def test_summary_accepts_valid_types() -> None:
    summary: Summary = {
        "sub_question": "What is a battery?",
        "content": "A battery stores energy chemically.",
        "tokens_used": 42,
        "model": "claude-haiku-4-5-20251001",
        "cost_usd": 0.0001,
    }
    assert TypeAdapter(Summary).validate_python(summary) == summary


def test_summary_rejects_non_integer_tokens() -> None:
    bad = {
        "sub_question": "What is a battery?",
        "content": "A battery stores energy chemically.",
        "tokens_used": "lots",  # wrong type: str where int expected
        "model": "claude-haiku-4-5-20251001",
        "cost_usd": 0.0001,
    }
    with pytest.raises(ValidationError):
        TypeAdapter(Summary).validate_python(bad)


def test_search_result_accepts_valid_types() -> None:
    result: SearchResult = {
        "sub_question": "What is a battery?",
        "results": [{"title": "Batteries 101", "url": "https://example.com"}],
        "node_id": "searcher_0",
    }
    assert TypeAdapter(SearchResult).validate_python(result) == result


def test_search_result_rejects_non_list_results() -> None:
    bad = {
        "sub_question": "What is a battery?",
        "results": {"title": "not a list"},  # wrong type: dict where list expected
        "node_id": "searcher_0",
    }
    with pytest.raises(ValidationError):
        TypeAdapter(SearchResult).validate_python(bad)


def test_research_state_accepts_full_state() -> None:
    state: ResearchState = {
        "question": "How do electric cars work?",
        "sub_questions": ["What is a battery?"],
        "search_results": [],
        "summaries": [],
        "report_intro": "",
        "report_conclusion": "",
        "final_report": "",
        "cost_log": [],
        "error": None,
    }
    assert TypeAdapter(ResearchState).validate_python(state) == state


def test_research_state_rejects_non_list_sub_questions() -> None:
    bad: dict[str, object] = {
        "question": "How do electric cars work?",
        "sub_questions": "not-a-list",  # wrong type: str where list expected
        "search_results": [],
        "summaries": [],
        "final_report": "",
        "cost_log": [],
        "error": None,
    }
    with pytest.raises(ValidationError):
        TypeAdapter(ResearchState).validate_python(bad)
