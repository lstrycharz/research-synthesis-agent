"""Graph wiring: fan-out/fan-in routing, with all agents mocked (no LLM, no network).

We test the routing shape, not agent behavior: fan_out_research produces one Send per
sub-question (capped by MAX_SUB_QUESTIONS), and the compiled graph threads state from
decompose -> research (x N) -> assemble -> reporter -> END.
"""

import pytest
from langgraph.types import Send

from src.graph import build_graph, fan_out_research


def _cost_entry(node: str) -> dict[str, object]:
    return {
        "node": node,
        "model": "m",
        "input_tokens": 1,
        "output_tokens": 1,
        "cost_usd": 0.0,
        "latency_ms": 1,
    }


def test_fan_out_research_one_send_per_subquestion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "y")
    sends = fan_out_research({"sub_questions": ["q1", "q2", "q3"]})
    assert len(sends) == 3
    assert all(isinstance(s, Send) and s.node == "research" for s in sends)
    assert [s.arg["index"] for s in sends] == [0, 1, 2]
    assert [s.arg["sub_question"] for s in sends] == ["q1", "q2", "q3"]


def test_fan_out_research_caps_at_max_sub_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "y")
    monkeypatch.setenv("MAX_SUB_QUESTIONS", "2")
    sends = fan_out_research({"sub_questions": ["q1", "q2", "q3", "q4", "q5"]})
    assert len(sends) == 2  # capped


async def test_graph_routes_end_to_end_with_mocked_agents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "y")

    async def fake_decompose(state: dict[str, object]) -> dict[str, object]:
        return {"sub_questions": ["q1", "q2"], "cost_log": [_cost_entry("supervisor_decompose")]}

    async def fake_searcher(payload: dict[str, object]) -> dict[str, object]:
        return {
            "search_results": [
                {
                    "sub_question": payload["sub_question"],
                    "results": [],
                    "node_id": f"searcher_{payload['index']}",
                }
            ]
        }

    async def fake_summarizer(search_result: dict[str, object]) -> dict[str, object]:
        return {
            "summaries": [
                {
                    "sub_question": search_result["sub_question"],
                    "content": "c",
                    "tokens_used": 1,
                    "model": "m",
                    "cost_usd": 0.0,
                }
            ],
            "cost_log": [_cost_entry("summarizer")],
        }

    async def fake_assemble(state: dict[str, object]) -> dict[str, object]:
        summaries = state["summaries"]
        assert isinstance(summaries, list)
        assert len(summaries) == 2  # fan-in complete: both branches accumulated before assemble
        return {
            "report_intro": "INTRO",
            "report_conclusion": "CONCL",
            "cost_log": [_cost_entry("supervisor_assemble")],
        }

    def fake_reporter(state: dict[str, object]) -> dict[str, object]:
        summaries = state["summaries"]
        assert isinstance(summaries, list)
        return {"final_report": f"REPORT with {len(summaries)} sections"}

    monkeypatch.setattr("src.graph.decompose_node", fake_decompose)
    monkeypatch.setattr("src.graph.searcher_node", fake_searcher)
    monkeypatch.setattr("src.graph.summarizer_node", fake_summarizer)
    monkeypatch.setattr("src.graph.assemble_node", fake_assemble)
    monkeypatch.setattr("src.graph.reporter_node", fake_reporter)

    graph = build_graph()
    final = await graph.ainvoke({"question": "How do EVs work?"}, config={"recursion_limit": 25})

    assert len(final["summaries"]) == 2  # both research branches fanned in
    assert final["report_intro"] == "INTRO"
    assert "2 sections" in final["final_report"]
    # decompose (1) + summarizer x2 (2) + assemble (1) = 4 cost entries accumulated
    assert len(final["cost_log"]) == 4
