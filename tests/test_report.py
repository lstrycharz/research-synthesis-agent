"""The reporter node assembles the final Markdown report from state.

Chunk 8 ships a minimal reporter (enough for the graph to reach END); Chunk 9 enriches it
(source attribution, cost-table row, polish).
"""

from src.report import reporter_node


def test_reporter_node_builds_final_report() -> None:
    state: dict[str, object] = {
        "question": "How do EVs work?",
        "report_intro": "This is the intro.",
        "report_conclusion": "This is the conclusion.",
        "summaries": [
            {
                "sub_question": "What is a battery?",
                "content": "Batteries store energy.",
                "tokens_used": 1,
                "model": "m",
                "cost_usd": 0.0,
            }
        ],
    }
    update = reporter_node(state)
    report = update["final_report"]
    assert isinstance(report, str)
    assert "How do EVs work?" in report
    assert "This is the intro." in report
    assert "What is a battery?" in report
    assert "Batteries store energy." in report
    assert "This is the conclusion." in report
