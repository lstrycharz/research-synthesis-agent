"""Graph state — the shared 'clipboard' every node reads from and writes to.

LangGraph state is a TypedDict. List fields that parallel workers write to carry an
`operator.add` reducer so concurrent appends accumulate instead of overwriting each
other (fully explained when we wire the graph). The single-writer fields are plain.

Node functions return a *partial* update — a plain ``dict[str, object]`` with only the
keys that node changed — not a full ``ResearchState``. LangGraph merges each partial
into the running state (applying reducers). Type node returns as ``dict[str, object]``.
"""

import operator
from typing import Annotated, NotRequired, TypedDict


class SearchResult(TypedDict):
    """Raw Tavily results for one sub-question, produced by a searcher node."""

    sub_question: str
    results: list[dict[str, object]]  # Tavily result objects
    node_id: str
    error: NotRequired[str | None]  # set when the search failed; summarizer handles it


class Summary(TypedDict):
    """A condensed section written by a summarizer node."""

    sub_question: str
    content: str
    tokens_used: int
    model: str
    cost_usd: float


class CostEntry(TypedDict):
    """One row per LLM call: what it cost and how long it took."""

    node: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int


class ResearchState(TypedDict):
    """The full state threaded through the graph from START to END."""

    question: str
    sub_questions: list[str]
    search_results: Annotated[list[SearchResult], operator.add]
    summaries: Annotated[list[Summary], operator.add]
    # Written by the supervisor's assemble step (single writer); read by the reporter.
    report_intro: str
    report_conclusion: str
    final_report: str
    cost_log: Annotated[list[CostEntry], operator.add]
    # Supervisor-only (single writer). Worker failures go into SearchResult.error;
    # two parallel nodes writing this in one superstep would raise InvalidUpdateError.
    error: str | None
