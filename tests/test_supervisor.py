"""The supervisor's decompose half: split a question into 3-5 sub-questions.

Structured output is enforced by the DecomposedQuestion Pydantic model (3-5 items). The
deep core `run_decompose` takes an `invoke` callable returning langchain's include_raw
dict ({"raw", "parsed", "parsing_error"}), so tests need no real model.
"""

from collections.abc import Awaitable, Callable

import pytest
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import ValidationError

from src.agents.supervisor import DecomposedQuestion, decompose_node, run_decompose

InvokeFn = Callable[[list[BaseMessage]], Awaitable[dict[str, object]]]

_SONNET = "claude-sonnet-4-6"


def _raw(input_tokens: int, output_tokens: int) -> AIMessage:
    return AIMessage(
        content="",
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


def _invoke_returning(result: dict[str, object]) -> InvokeFn:
    async def _invoke(messages: list[BaseMessage]) -> dict[str, object]:
        return result

    return _invoke


def test_decomposed_question_accepts_three_to_five() -> None:
    three = DecomposedQuestion(sub_questions=["a", "b", "c"], research_intent="x")
    five = DecomposedQuestion(sub_questions=["a", "b", "c", "d", "e"], research_intent="x")
    assert len(three.sub_questions) == 3
    assert len(five.sub_questions) == 5


def test_decomposed_question_rejects_fewer_than_three() -> None:
    with pytest.raises(ValidationError):
        DecomposedQuestion(sub_questions=["a", "b"], research_intent="x")


def test_decomposed_question_rejects_more_than_five() -> None:
    with pytest.raises(ValidationError):
        DecomposedQuestion(sub_questions=["a", "b", "c", "d", "e", "f"], research_intent="x")


async def test_run_decompose_returns_parsed_and_cost() -> None:
    parsed = DecomposedQuestion(
        sub_questions=["What is a battery?", "How does the motor work?", "How is it charged?"],
        research_intent="Understand how EVs function.",
    )
    invoke = _invoke_returning(
        {"raw": _raw(2000, 1000), "parsed": parsed, "parsing_error": None}
    )
    decomposed, entry = await run_decompose(
        "How do electric cars work?", model_name=_SONNET, invoke=invoke
    )
    assert decomposed.sub_questions == parsed.sub_questions
    assert entry["node"] == "supervisor_decompose"
    assert entry["model"] == _SONNET
    assert round(entry["cost_usd"], 6) == 0.021  # (2000*$3 + 1000*$15) / 1e6


async def test_run_decompose_passes_question_into_prompt() -> None:
    seen: dict[str, list[BaseMessage]] = {}
    parsed = DecomposedQuestion(sub_questions=["a", "b", "c"], research_intent="i")

    async def capturing(messages: list[BaseMessage]) -> dict[str, object]:
        seen["messages"] = messages
        return {"raw": _raw(1, 1), "parsed": parsed, "parsing_error": None}

    await run_decompose("How do EVs work?", model_name=_SONNET, invoke=capturing)
    human = seen["messages"][1]
    text = human.content if isinstance(human.content, str) else str(human.content)
    assert "How do EVs work?" in text


async def test_run_decompose_missing_usage_records_zero_cost() -> None:
    parsed = DecomposedQuestion(sub_questions=["a", "b", "c"], research_intent="i")
    invoke = _invoke_returning(
        {"raw": AIMessage(content=""), "parsed": parsed, "parsing_error": None}
    )
    _, entry = await run_decompose("q", model_name=_SONNET, invoke=invoke)
    assert entry["cost_usd"] == 0.0
    assert entry["input_tokens"] == 0


async def test_run_decompose_raises_on_parse_failure() -> None:
    invoke = _invoke_returning(
        {"raw": _raw(10, 0), "parsed": None, "parsing_error": "only produced 2 sub-questions"}
    )
    with pytest.raises(ValueError):
        await run_decompose("q", model_name=_SONNET, invoke=invoke)


async def test_decompose_node_sets_sub_questions_and_cost_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("TAVILY_API_KEY", "y")

    parsed = DecomposedQuestion(
        sub_questions=["a", "b", "c"], research_intent="intent"
    )
    entry = {
        "node": "supervisor_decompose",
        "model": _SONNET,
        "input_tokens": 10,
        "output_tokens": 5,
        "cost_usd": 0.001,
        "latency_ms": 100,
    }

    async def stub(
        question: str, *, model_name: str, invoke: InvokeFn
    ) -> tuple[DecomposedQuestion, dict[str, object]]:
        return parsed, entry

    monkeypatch.setattr("src.agents.supervisor.run_decompose", stub)
    update = await decompose_node({"question": "How do electric cars work?"})

    assert update["sub_questions"] == ["a", "b", "c"]
    assert isinstance(update["cost_log"], list)
    assert update["cost_log"][0]["node"] == "supervisor_decompose"
