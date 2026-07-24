"""Reporter: assemble the final Markdown report from graph state.

Chunk 8 ships a minimal-but-real assembler (intro + one section per summary + conclusion),
enough for the graph to reach END. Chunk 9 enriches it: source attribution, a cost-table
row, and formatting polish.
"""

from typing import cast

from src.state import Summary


def reporter_node(state: dict[str, object]) -> dict[str, object]:
    """LangGraph node: build state['final_report'] from the assembled pieces + summaries."""
    question = str(state.get("question", ""))
    intro = str(state.get("report_intro", ""))
    conclusion = str(state.get("report_conclusion", ""))
    summaries = cast("list[Summary]", state.get("summaries", []))

    parts: list[str] = [f"# Research Report: {question}", intro]
    for summary in summaries:
        parts.append(f"## {summary['sub_question']}\n\n{summary['content']}")
    parts.append(conclusion)

    report = "\n\n".join(part for part in parts if part)
    return {"final_report": report}
