"""Reporter: assemble the final Markdown report from graph state. Pure — no I/O.

Builds: title, executive summary, one section per sub-question (summary + its sources),
conclusion, and an in-report cost table from the cost log. The one-line-per-run append to
docs/cost-breakdown.md (which needs wall-clock latency) is done by main.py via write_cost_row.
"""

from typing import cast

from src.state import CostEntry, SearchResult, Summary


def _oneline(text: str) -> str:
    """Collapse whitespace so a value can't break a heading or table row onto a new line."""
    return " ".join(text.split())


def _escape_link_text(text: str) -> str:
    """Escape brackets so a scraped title can't close the link text early."""
    return _oneline(text).replace("[", r"\[").replace("]", r"\]")


def _safe_url(url: str) -> str:
    """Allowlist http/https and encode parens; return '' for anything unsafe (-> plain title)."""
    url = "".join(url.split())  # URLs never contain whitespace
    if not url.lower().startswith(("http://", "https://")):
        return ""  # drop javascript:, data:, etc.
    return url.replace("(", "%28").replace(")", "%29")


def _format_sources(results: list[dict[str, object]]) -> str:
    if not results:
        return ""
    lines = ["**Sources:**"]
    for result in results:
        title = _escape_link_text(str(result.get("title", "(untitled)")))
        url = _safe_url(str(result.get("url", "")))
        lines.append(f"- [{title}]({url})" if url else f"- {title}")
    return "\n".join(lines)


def _format_cost_table(cost_log: list[CostEntry]) -> str:
    total = sum(float(entry["cost_usd"]) for entry in cost_log)
    lines = [
        "## Run Cost",
        "",
        "| Node | Model | Input | Output | Cost |",
        "|------|-------|-------|--------|------|",
    ]
    for entry in cost_log:
        lines.append(
            f"| {entry['node']} | {entry['model']} "
            f"| {entry['input_tokens']} | {entry['output_tokens']} "
            f"| ${float(entry['cost_usd']):.6f} |"
        )
    lines.append("")
    lines.append(f"**Total: ${total:.6f}**")
    return "\n".join(lines)


def reporter_node(state: dict[str, object]) -> dict[str, object]:
    """LangGraph node: build state['final_report'] from the assembled pieces + summaries."""
    question = _oneline(str(state.get("question", "")))
    intro = str(state.get("report_intro", ""))
    conclusion = str(state.get("report_conclusion", ""))
    summaries = cast("list[Summary]", state.get("summaries", []))
    search_results = cast("list[SearchResult]", state.get("search_results", []))
    cost_log = cast("list[CostEntry]", state.get("cost_log", []))

    # Map each sub-question to the raw results the searcher found for it. Merge (not
    # overwrite) if a sub-question ever repeats, so no source list is silently dropped.
    sources_by_question: dict[str, list[dict[str, object]]] = {}
    for sr in search_results:
        sources_by_question.setdefault(sr["sub_question"], []).extend(sr.get("results", []))

    parts: list[str] = [f"# Research Report: {question}"]
    if intro:
        parts.append(f"## Executive Summary\n\n{intro}")

    for summary in summaries:
        # Heading is one-lined so an LLM-emitted newline can't break the `##` heading; the
        # lookup key stays raw to match how searcher/summarizer threaded the sub-question.
        section = [f"## {_oneline(summary['sub_question'])}", summary["content"]]
        sources = _format_sources(sources_by_question.get(summary["sub_question"], []))
        if sources:
            section.append(sources)
        parts.append("\n\n".join(section))

    if conclusion:
        parts.append(f"## Conclusion\n\n{conclusion}")

    if cost_log:
        parts.append(_format_cost_table(cost_log))

    return {"final_report": "\n\n".join(parts)}
