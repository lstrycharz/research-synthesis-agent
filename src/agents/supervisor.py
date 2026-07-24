"""Supervisor node — the boss. It appears twice in the graph.

Decompose (first visit): split the raw question into 3-5 atomic sub-questions using
structured output. The DecomposedQuestion Pydantic model enforces the 3-5 count. Decompose
is essential — a failure raises (no valid split, no report).

Assemble (second visit): after all summaries return, write the report's executive summary
and conclusion (structured AssembledReport). Assemble is NOT essential — a parse failure
degrades to empty placeholders so the report still ships with its sections.

Both use langchain's include_raw mode so we get the parsed object AND the raw AIMessage
(for token cost). Model construction + Langfuse wiring live in _llm.py.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.agents._llm import build_chat_model, langfuse_config
from src.config import get_settings
from src.observability import log_llm_call
from src.state import CostEntry, Summary

logger = logging.getLogger(__name__)

_MAX_TOKENS = 1024

# Returns langchain's include_raw dict: {"raw": AIMessage, "parsed": obj|None, "parsing_error": ...}
StructuredInvokeFn = Callable[[list[BaseMessage]], Awaitable[dict[str, object]]]

_DECOMPOSE_SYSTEM = (
    "You are a research director. Given a user's open-ended question, break it into 3-5 "
    "atomic, independently researchable sub-questions that together cover the question. Each "
    "sub-question must stand alone (no pronouns referring to the others). Also state, in one "
    "sentence, what the user actually needs to know."
)

_ASSEMBLE_SYSTEM = (
    "You are a research director assembling a report. Given the original question and the "
    "section summaries, write a cohesive executive summary and a conclusion that synthesize "
    "the findings. Do not repeat the section summaries verbatim — add connective insight. "
    "Keep each to 2-4 sentences."
)


class DecomposedQuestion(BaseModel):
    """Structured output for decomposition — Pydantic enforces the 3-5 count."""

    sub_questions: list[str] = Field(
        min_length=3,
        max_length=5,
        description="3-5 specific, independently researchable sub-questions",
    )
    research_intent: str = Field(description="One sentence: what the user actually needs to know")


class AssembledReport(BaseModel):
    """Structured output for assembly — the report's framing prose."""

    executive_summary: str = Field(description="2-4 sentence executive summary of the findings")
    conclusion: str = Field(description="2-4 sentence conclusion; do not repeat sections verbatim")


def _build_decompose_messages(question: str) -> list[BaseMessage]:
    return [SystemMessage(content=_DECOMPOSE_SYSTEM), HumanMessage(content=question)]


def _format_summaries(summaries: list[Summary]) -> str:
    return "\n\n".join(f"Sub-question: {s['sub_question']}\n{s['content']}" for s in summaries)


def _build_assemble_messages(question: str, summaries: list[Summary]) -> list[BaseMessage]:
    human = HumanMessage(
        content=(
            f"Original question: {question}\n\n"
            f"Section summaries:\n{_format_summaries(summaries)}\n\n"
            "Write the executive summary and conclusion."
        )
    )
    return [SystemMessage(content=_ASSEMBLE_SYSTEM), human]


def _tokens(raw: object) -> tuple[int, int]:
    """Pull (input, output) token counts off the raw AIMessage; 0s if unavailable."""
    usage = getattr(raw, "usage_metadata", None)
    if not usage:
        logger.warning("supervisor: raw response missing usage_metadata; cost recorded as 0")
        return 0, 0
    return usage["input_tokens"], usage["output_tokens"]


async def run_decompose(
    question: str,
    *,
    model_name: str,
    invoke: StructuredInvokeFn,
) -> tuple[DecomposedQuestion, CostEntry]:
    """Decompose the question into a valid 3-5 sub-question set.

    Raises ValueError if the model can't produce one — decompose is essential.
    """
    start = time.perf_counter()
    result = await invoke(_build_decompose_messages(question))
    latency_ms = int((time.perf_counter() - start) * 1000)

    parsed = result.get("parsed")
    if not isinstance(parsed, DecomposedQuestion):
        spent_in, spent_out = _tokens(result.get("raw"))
        logger.error(
            "decompose: parse failure after %d in / %d out tokens (aborting run)",
            spent_in,
            spent_out,
        )
        raise ValueError(
            f"Failed to decompose into 3-5 sub-questions: {result.get('parsing_error')}"
        )

    input_tokens, output_tokens = _tokens(result.get("raw"))
    entry = log_llm_call(
        node="supervisor_decompose",
        model=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )
    return parsed, entry


async def run_assemble(
    question: str,
    summaries: list[Summary],
    *,
    model_name: str,
    invoke: StructuredInvokeFn,
) -> tuple[AssembledReport, CostEntry]:
    """Write the report's executive summary + conclusion.

    Assemble is not essential: a parse failure degrades to empty placeholders (the report
    still has its sections) rather than aborting the run.
    """
    start = time.perf_counter()
    try:
        result = await invoke(_build_assemble_messages(question, summaries))
    except Exception as exc:  # noqa: BLE001 - assemble is non-essential; report ships without it
        logger.warning("assemble: model call failed; using placeholder intro/conclusion: %s", exc)
        entry = log_llm_call(
            node="supervisor_assemble",
            model=model_name,
            input_tokens=0,
            output_tokens=0,
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
        return AssembledReport(executive_summary="", conclusion=""), entry
    latency_ms = int((time.perf_counter() - start) * 1000)

    parsed = result.get("parsed")
    if not isinstance(parsed, AssembledReport):
        logger.warning(
            "assemble: parse failure; using placeholder intro/conclusion: %s",
            result.get("parsing_error"),
        )
        parsed = AssembledReport(executive_summary="", conclusion="")

    input_tokens, output_tokens = _tokens(result.get("raw"))
    entry = log_llm_call(
        node="supervisor_assemble",
        model=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )
    return parsed, entry


async def decompose_node(state: dict[str, object]) -> dict[str, object]:
    """LangGraph node: decompose state['question'] into sub_questions + a cost entry."""
    settings = get_settings()
    question = str(state["question"])

    model = build_chat_model(settings, model_name=settings.supervisor_model, max_tokens=_MAX_TOKENS)
    structured = model.with_structured_output(DecomposedQuestion, include_raw=True)
    config = langfuse_config(settings)

    async def _invoke(messages: list[BaseMessage]) -> dict[str, object]:
        return cast(dict[str, object], await structured.ainvoke(messages, config=config))

    decomposed, entry = await run_decompose(
        question, model_name=settings.supervisor_model, invoke=_invoke
    )
    return {"sub_questions": decomposed.sub_questions, "cost_log": [entry]}


async def assemble_node(state: dict[str, object]) -> dict[str, object]:
    """LangGraph node: write the report intro/conclusion from the summaries + a cost entry."""
    settings = get_settings()
    question = str(state["question"])
    summaries = cast(list[Summary], state.get("summaries", []))

    model = build_chat_model(settings, model_name=settings.supervisor_model, max_tokens=_MAX_TOKENS)
    structured = model.with_structured_output(AssembledReport, include_raw=True)
    config = langfuse_config(settings)

    async def _invoke(messages: list[BaseMessage]) -> dict[str, object]:
        return cast(dict[str, object], await structured.ainvoke(messages, config=config))

    report, entry = await run_assemble(
        question, summaries, model_name=settings.supervisor_model, invoke=_invoke
    )
    return {
        "report_intro": report.executive_summary,
        "report_conclusion": report.conclusion,
        "cost_log": [entry],
    }
