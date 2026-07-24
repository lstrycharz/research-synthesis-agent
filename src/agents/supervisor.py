"""Supervisor node — the boss. This module holds the decompose half.

Decompose: split the raw question into 3-5 atomic sub-questions using structured output.
The DecomposedQuestion Pydantic model enforces the 3-5 count; langchain's include_raw mode
returns both the parsed object and the raw AIMessage so we can still track token cost.
(The assemble half is added in the next chunk.)
"""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field, SecretStr

from src.config import get_settings
from src.observability import get_langfuse_client, log_llm_call
from src.state import CostEntry

logger = logging.getLogger(__name__)

_MAX_TOKENS = 1024

# Returns langchain's include_raw dict: {"raw": AIMessage, "parsed": obj|None, "parsing_error": ...}
DecomposeInvokeFn = Callable[[list[BaseMessage]], Awaitable[dict[str, object]]]

_DECOMPOSE_SYSTEM = (
    "You are a research director. Given a user's open-ended question, break it into 3-5 "
    "atomic, independently researchable sub-questions that together cover the question. Each "
    "sub-question must stand alone (no pronouns referring to the others). Also state, in one "
    "sentence, what the user actually needs to know."
)


class DecomposedQuestion(BaseModel):
    """Structured output for decomposition — Pydantic enforces the 3-5 count."""

    sub_questions: list[str] = Field(
        min_length=3,
        max_length=5,
        description="3-5 specific, independently researchable sub-questions",
    )
    research_intent: str = Field(description="One sentence: what the user actually needs to know")


def _build_decompose_messages(question: str) -> list[BaseMessage]:
    return [SystemMessage(content=_DECOMPOSE_SYSTEM), HumanMessage(content=question)]


def _tokens(raw: object) -> tuple[int, int]:
    """Pull (input, output) token counts off the raw AIMessage; 0s if unavailable."""
    usage = getattr(raw, "usage_metadata", None)
    if not usage:
        logger.warning("decompose: raw response missing usage_metadata; cost recorded as 0")
        return 0, 0
    return usage["input_tokens"], usage["output_tokens"]


async def run_decompose(
    question: str,
    *,
    model_name: str,
    invoke: DecomposeInvokeFn,
) -> tuple[DecomposedQuestion, CostEntry]:
    """Decompose the question. Returns (DecomposedQuestion, CostEntry).

    Raises ValueError if the model can't produce a valid 3-5 sub-question set — decompose
    is essential, so a failure here should stop the run rather than produce a broken report.
    """
    start = time.perf_counter()
    result = await invoke(_build_decompose_messages(question))
    latency_ms = int((time.perf_counter() - start) * 1000)

    parsed = result.get("parsed")
    if not isinstance(parsed, DecomposedQuestion):
        # A real API call already happened; record the spend before aborting the run.
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


async def decompose_node(state: dict[str, object]) -> dict[str, object]:
    """LangGraph node: decompose state['question'] into sub_questions + a cost entry."""
    settings = get_settings()
    question = str(state["question"])

    from langchain_anthropic import ChatAnthropic

    model = ChatAnthropic(  # type: ignore[call-arg]  # model/max_tokens are pydantic aliases
        model=settings.supervisor_model,
        api_key=SecretStr(settings.anthropic_api_key),
        max_tokens=_MAX_TOKENS,
    )
    structured = model.with_structured_output(DecomposedQuestion, include_raw=True)

    config: RunnableConfig = {}
    if get_langfuse_client(settings) is not None:
        from langfuse.langchain import CallbackHandler

        config = {"callbacks": [CallbackHandler()]}

    async def _invoke(messages: list[BaseMessage]) -> dict[str, object]:
        response = await structured.ainvoke(messages, config=config)
        return cast(dict[str, object], response)

    decomposed, entry = await run_decompose(
        question, model_name=settings.supervisor_model, invoke=_invoke
    )
    return {"sub_questions": decomposed.sub_questions, "cost_log": [entry]}
