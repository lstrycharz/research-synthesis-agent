"""The StateGraph: fan-out/fan-in wiring for the research pipeline.

    START -> decompose -> [Send research x N sub-questions] -> assemble -> reporter -> END

The supervisor decomposes into sub-questions; a conditional edge fans out one `research`
branch per sub-question via Send (capped at MAX_SUB_QUESTIONS). Each research branch runs
searcher then summarizer, appending to the operator.add reducer channels. LangGraph waits
for all branches (fan-in) before assemble writes the intro/conclusion; the reporter builds
the final Markdown.
"""

from typing import cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from src.agents.searcher import searcher_node
from src.agents.summarizer import summarizer_node
from src.agents.supervisor import assemble_node, decompose_node
from src.config import get_settings
from src.report import reporter_node
from src.state import ResearchState


def fan_out_research(state: dict[str, object]) -> list[Send]:
    """Conditional edge: one `research` Send per sub-question, capped at MAX_SUB_QUESTIONS."""
    settings = get_settings()
    sub_questions = cast("list[str]", state["sub_questions"])
    capped = sub_questions[: settings.max_sub_questions]
    return [Send("research", {"sub_question": q, "index": i}) for i, q in enumerate(capped)]


async def research_node(payload: dict[str, object]) -> dict[str, object]:
    """One sub-question end-to-end: search, then summarize. Returns a merged partial update.

    Composes the two worker nodes so each Send branch handles its own sub-question
    independently (search results + summary + cost all produced in this branch).
    """
    search_update = await searcher_node(payload)
    search_results = cast("list[dict[str, object]]", search_update["search_results"])
    summary_update = await summarizer_node(search_results[0])
    return {**search_update, **summary_update}


def build_graph() -> CompiledStateGraph:
    """Build and compile the research StateGraph."""
    graph: StateGraph = StateGraph(ResearchState)
    # Nodes take dict[str, object] (they receive Send payloads / partial state); LangGraph
    # types add_node against the ResearchState schema, so these mismatches are expected.
    graph.add_node("decompose", decompose_node)  # type: ignore[type-var]
    graph.add_node("research", research_node)  # type: ignore[arg-type]
    graph.add_node("assemble", assemble_node)  # type: ignore[type-var]
    graph.add_node("reporter", reporter_node)  # type: ignore[type-var]

    graph.add_edge(START, "decompose")
    graph.add_conditional_edges("decompose", fan_out_research, ["research"])
    graph.add_edge("research", "assemble")
    graph.add_edge("assemble", "reporter")
    graph.add_edge("reporter", END)

    return graph.compile()
