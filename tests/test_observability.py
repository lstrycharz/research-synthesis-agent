"""Cost math, the local cost-table writer, and the Langfuse-optional client.

Cost accuracy is asserted to 6 decimal places (per the build spec). The Langfuse client
must be None when keys are absent so the pipeline runs with zero observability config.
"""

import logging
from pathlib import Path

import pytest

from src.config import Settings
from src.observability import (
    calculate_cost,
    get_langfuse_client,
    log_llm_call,
    write_cost_row,
)


def test_calculate_cost_haiku_matches_hand_computation() -> None:
    # (1000 * $1.00 + 500 * $5.00) / 1e6 = 3500 / 1e6 = $0.0035
    cost = calculate_cost("claude-haiku-4-5-20251001", input_tokens=1000, output_tokens=500)
    assert round(cost, 6) == 0.0035


def test_calculate_cost_sonnet_matches_hand_computation() -> None:
    # (2000 * $3.00 + 1000 * $15.00) / 1e6 = 21000 / 1e6 = $0.021
    cost = calculate_cost("claude-sonnet-4-6", input_tokens=2000, output_tokens=1000)
    assert round(cost, 6) == 0.021


def test_calculate_cost_rejects_unknown_model() -> None:
    with pytest.raises(ValueError):
        calculate_cost("gpt-4", input_tokens=1, output_tokens=1)


def test_log_llm_call_returns_cost_entry_with_computed_cost() -> None:
    entry = log_llm_call(
        node="summarizer",
        model="claude-haiku-4-5-20251001",
        input_tokens=1000,
        output_tokens=500,
        latency_ms=1200,
    )
    assert entry["node"] == "summarizer"
    assert entry["model"] == "claude-haiku-4-5-20251001"
    assert entry["input_tokens"] == 1000
    assert entry["output_tokens"] == 500
    assert entry["latency_ms"] == 1200
    assert round(entry["cost_usd"], 6) == 0.0035


def test_write_cost_row_appends_row(tmp_path: Path) -> None:
    doc = tmp_path / "cost-breakdown.md"
    write_cost_row(
        path=doc,
        date="2026-07-25",
        question="What is LangGraph?",
        sub_question_count=3,
        total_cost_usd=0.0043,
        latency_s=1.2,
        node_count=12,
    )
    row = doc.read_text(encoding="utf-8")
    assert "What is LangGraph?" in row
    assert "3 sub-questions" in row
    assert "$0.0043" in row
    assert "1.2s" in row
    assert "12 nodes" in row


def test_write_cost_row_escapes_pipe_in_question(tmp_path: Path) -> None:
    doc = tmp_path / "cost-breakdown.md"
    write_cost_row(
        path=doc,
        date="2026-07-25",
        question="A | B?",  # a raw pipe would break the markdown table
        sub_question_count=1,
        total_cost_usd=0.001,
        latency_s=0.5,
        node_count=4,
    )
    row = doc.read_text(encoding="utf-8")
    assert "A \\| B?" in row


def test_write_cost_row_collapses_newlines_in_question(tmp_path: Path) -> None:
    doc = tmp_path / "cost-breakdown.md"
    write_cost_row(
        path=doc,
        date="2026-07-25",
        question="A\r\nB",  # CR/LF would break the row onto a new line
        sub_question_count=1,
        total_cost_usd=0.001,
        latency_s=0.5,
        node_count=4,
    )
    lines = [ln for ln in doc.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1  # the question did not spill onto a second line
    assert "A B" in lines[0]


def test_get_langfuse_client_returns_none_without_keys() -> None:
    settings = Settings(_env_file=None, anthropic_api_key="x", tavily_api_key="y")  # type: ignore[call-arg]
    assert get_langfuse_client(settings) is None


def test_get_langfuse_client_builds_client_when_keys_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeLangfuse:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr("langfuse.Langfuse", FakeLangfuse)
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        anthropic_api_key="x",
        tavily_api_key="y",
        langfuse_public_key="pk-lf-1",
        langfuse_secret_key="sk-lf-1",
    )
    client = get_langfuse_client(settings)
    assert isinstance(client, FakeLangfuse)


def test_get_langfuse_client_warns_on_partial_config(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Only the public key set — tracing must disable, but warn so the user isn't confused.
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        anthropic_api_key="x",
        tavily_api_key="y",
        langfuse_public_key="pk-only",
    )
    with caplog.at_level(logging.WARNING):
        client = get_langfuse_client(settings)
    assert client is None
    assert "partially configured" in caplog.text
