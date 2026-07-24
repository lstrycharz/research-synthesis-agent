"""CLI entrypoint: startup validation + the run orchestration, network fully mocked.

We test the deterministic core of main.py — fail-fast model validation, path-safe output
filenames, and that a run writes the report file and appends exactly one cost row — by
injecting a fake compiled graph. The real Anthropic/Tavily/Langfuse call happens only in
the live E2E run (Chunk 10), never in the test suite.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from langgraph.graph.state import CompiledStateGraph

from src.config import Settings
from src.main import build_output_path, main, question_from_argv, run_research, validate_models

_COST_HEADER = (
    "| Date | Question | Sub-questions | Cost (USD) | Latency | Nodes |\n"
    "|------|----------|---------------|------------|---------|-------|\n"
)


def _settings(**overrides: str) -> Settings:
    """Build Settings for a test — _env_file=None keeps it hermetic (ignores the real .env)."""
    base: dict[str, object] = {"anthropic_api_key": "a", "tavily_api_key": "t", "_env_file": None}
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_validate_models_rejects_unpriced_model() -> None:
    settings = _settings(supervisor_model="made-up-model")
    with pytest.raises(ValueError, match="MODEL_COSTS"):
        validate_models(settings)


def test_validate_models_accepts_configured_defaults() -> None:
    validate_models(_settings())  # default supervisor/worker models are priced -> no raise


def test_build_output_path_slugifies_and_stays_contained(tmp_path: Path) -> None:
    now = datetime(2026, 7, 24, 15, 30, 5, tzinfo=UTC)
    path = build_output_path("How do EVs work?? /../etc/passwd", now=now, outputs_dir=tmp_path)
    assert path.parent == tmp_path.resolve()  # never escapes the outputs dir
    assert path.name.startswith("20260724-153005-")
    assert path.suffix == ".md"
    assert "/" not in path.name and ".." not in path.name


def test_build_output_path_empty_question_falls_back(tmp_path: Path) -> None:
    now = datetime(2026, 7, 24, 15, 30, 5, tzinfo=UTC)
    path = build_output_path("!!!", now=now, outputs_dir=tmp_path)
    assert path.name == "20260724-153005-report.md"  # unsluggable -> 'report'


async def test_run_research_saves_report_and_appends_one_cost_row(tmp_path: Path) -> None:
    settings = _settings()
    now = datetime(2026, 7, 24, 12, 0, 0, tzinfo=UTC)
    cost_doc = tmp_path / "cost.md"
    cost_doc.write_text(_COST_HEADER, encoding="utf-8")

    final_state: dict[str, object] = {
        "final_report": "# Research Report: Q\n\nbody",
        "sub_questions": ["a", "b"],
        "cost_log": [
            {"node": "supervisor_decompose", "model": "m", "input_tokens": 1,
             "output_tokens": 1, "cost_usd": 0.001, "latency_ms": 1},
            {"node": "summarizer", "model": "m", "input_tokens": 1,
             "output_tokens": 1, "cost_usd": 0.002, "latency_ms": 1},
        ],
    }

    class _FakeGraph:
        async def ainvoke(
            self, state: dict[str, object], *, config: dict[str, object]
        ) -> dict[str, object]:
            assert state["question"] == "Q"
            assert config["recursion_limit"] == 25
            return final_state

    path, returned = await run_research(
        "Q",
        settings=settings,
        graph=cast(CompiledStateGraph, _FakeGraph()),
        now=now,
        outputs_dir=tmp_path,
        cost_doc=cost_doc,
    )

    assert returned is final_state
    assert path.read_text(encoding="utf-8") == "# Research Report: Q\n\nbody"

    rows = cost_doc.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 3  # 2 header lines + exactly one appended run row
    row = rows[-1]
    assert "2026-07-24" in row
    assert "Q" in row
    assert "2 sub-questions" in row
    assert "$0.0030" in row  # 0.001 + 0.002, formatted to 4 decimals


def test_question_from_argv_joins_unquoted_words() -> None:
    assert question_from_argv(["prog", "how", "do", "EVs", "work"]) == "how do EVs work"


def test_question_from_argv_empty_when_no_args() -> None:
    assert question_from_argv(["prog"]) == ""


async def test_main_returns_usage_code_when_no_question() -> None:
    # No network touched: main bails on the empty-question guard before building anything.
    assert await main(["prog"]) == 2
