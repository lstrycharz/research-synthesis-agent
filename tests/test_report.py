"""The reporter node assembles the final Markdown report from state — pure, no I/O.

Enriched over the Chunk 8 minimal version: section headings, per-section source attribution
(from search_results), and an in-report cost table (from cost_log). The one-line-per-run
docs/cost-breakdown.md append (which needs wall-clock latency) lives in main.py.
"""

from src.report import reporter_node

_STATE: dict[str, object] = {
    "question": "How do electric cars work?",
    "report_intro": "EVs convert stored electrical energy into motion.",
    "report_conclusion": "In short, batteries, motors, and charging work together.",
    "summaries": [
        {
            "sub_question": "What is a battery?",
            "content": "A battery stores energy chemically.",
            "tokens_used": 100,
            "model": "claude-haiku-4-5-20251001",
            "cost_usd": 0.0003,
        }
    ],
    "search_results": [
        {
            "sub_question": "What is a battery?",
            "results": [{"title": "Batteries 101", "url": "https://example.com/batteries"}],
            "node_id": "searcher_0",
        }
    ],
    "cost_log": [
        {
            "node": "supervisor_decompose",
            "model": "claude-sonnet-4-6",
            "input_tokens": 200,
            "output_tokens": 100,
            "cost_usd": 0.002100,
            "latency_ms": 900,
        },
        {
            "node": "summarizer",
            "model": "claude-haiku-4-5-20251001",
            "input_tokens": 100,
            "output_tokens": 50,
            "cost_usd": 0.000350,
            "latency_ms": 700,
        },
    ],
}


def test_reporter_includes_title_intro_sections_conclusion() -> None:
    report = reporter_node(_STATE)["final_report"]
    assert isinstance(report, str)
    assert "# Research Report: How do electric cars work?" in report
    assert "EVs convert stored electrical energy into motion." in report
    assert "## What is a battery?" in report
    assert "A battery stores energy chemically." in report
    assert "batteries, motors, and charging work together." in report


def test_reporter_lists_sources_per_section() -> None:
    report = reporter_node(_STATE)["final_report"]
    assert isinstance(report, str)
    assert "Batteries 101" in report
    assert "https://example.com/batteries" in report


def test_reporter_includes_cost_total() -> None:
    report = reporter_node(_STATE)["final_report"]
    assert isinstance(report, str)
    # total = 0.002100 + 0.000350 = 0.002450
    assert "$0.002450" in report
    # per-node rows present
    assert "supervisor_decompose" in report
    assert "summarizer" in report


def test_reporter_handles_missing_search_results() -> None:
    state: dict[str, object] = {
        "question": "q",
        "report_intro": "i",
        "report_conclusion": "c",
        "summaries": [
            {
                "sub_question": "orphan question",
                "content": "some content",
                "tokens_used": 1,
                "model": "m",
                "cost_usd": 0.0,
            }
        ],
        "search_results": [],  # no matching sources
        "cost_log": [],
    }
    report = reporter_node(state)["final_report"]
    assert isinstance(report, str)
    assert "orphan question" in report  # section still rendered...
    assert "**Sources:**" not in report  # ...but no Sources block


def _state_with_source(result: dict[str, object]) -> dict[str, object]:
    return {
        "question": "q",
        "report_intro": "i",
        "report_conclusion": "c",
        "summaries": [
            {
                "sub_question": "sq",
                "content": "content",
                "tokens_used": 1,
                "model": "m",
                "cost_usd": 0.0,
            }
        ],
        "search_results": [{"sub_question": "sq", "results": [result], "node_id": "s0"}],
        "cost_log": [],
    }


def test_reporter_escapes_bracket_in_source_title() -> None:
    report = reporter_node(_state_with_source({"title": "Evil] title", "url": "https://ex.com"}))[
        "final_report"
    ]
    assert isinstance(report, str)
    assert "Evil\\] title" in report  # bracket escaped so it can't close the link early


def test_reporter_rejects_non_http_url_scheme() -> None:
    report = reporter_node(_state_with_source({"title": "Click me", "url": "javascript:alert(1)"}))[
        "final_report"
    ]
    assert isinstance(report, str)
    assert "javascript:" not in report  # dangerous scheme dropped
    assert "- Click me" in report  # falls back to a plain (non-link) bullet


def test_reporter_encodes_parens_in_url() -> None:
    report = reporter_node(_state_with_source({"title": "T", "url": "https://ex.com/a(b)c"}))[
        "final_report"
    ]
    assert isinstance(report, str)
    assert "https://ex.com/a%28b%29c" in report  # parens encoded so they don't break (url)


def test_reporter_source_without_url_renders_plain_bullet() -> None:
    report = reporter_node(_state_with_source({"title": "No link here"}))["final_report"]
    assert isinstance(report, str)
    assert "- No link here" in report


def test_reporter_source_without_title_uses_untitled() -> None:
    report = reporter_node(_state_with_source({"url": "https://ex.com"}))["final_report"]
    assert isinstance(report, str)
    assert "(untitled)" in report


def test_reporter_omits_cost_table_when_no_cost_log() -> None:
    report = reporter_node(_state_with_source({"title": "T", "url": "https://ex.com"}))[
        "final_report"
    ]
    assert isinstance(report, str)
    assert "## Run Cost" not in report
