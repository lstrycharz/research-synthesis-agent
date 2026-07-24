"""Observability: cost math, the local cost log, and an optional Langfuse client.

This module is the single source of truth for model pricing. Every LLM call routes its
token counts through ``log_llm_call`` to produce a ``CostEntry``. Langfuse tracing is
optional — ``get_langfuse_client`` returns ``None`` when keys are absent, so the pipeline
runs (and still tracks cost) with zero observability configuration.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.config import Settings
from src.state import CostEntry

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from langfuse import Langfuse

# Pricing in USD per 1,000,000 tokens. THE single source of truth — update only here.
# Verified 2026-07-24 against Anthropic's pricing docs:
#   Sonnet 5   = $2.00/$10.00  (INTRODUCTORY, through 2026-08-31; rises to $3.00/$15.00 on
#                Sep 1 2026 — bump this entry then, or logged supervisor cost drifts low).
#   Sonnet 4.6 = $3.00/$15.00
#   Haiku 4.5  = $1.00/$5.00
MODEL_COSTS: dict[str, dict[str, float]] = {
    "claude-sonnet-5": {"input": 2.00, "output": 10.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
}

_TOKENS_PER_UNIT = 1_000_000

# Repo-root docs/cost-breakdown.md (this file is src/observability.py).
DEFAULT_COST_DOC = Path(__file__).resolve().parent.parent / "docs" / "cost-breakdown.md"


def calculate_cost(model: str, *, input_tokens: int, output_tokens: int) -> float:
    """Return the USD cost of one call. Raises ValueError for an unknown model."""
    prices = MODEL_COSTS.get(model)
    if prices is None:
        raise ValueError(f"Unknown model (no pricing in MODEL_COSTS): {model!r}")
    return (input_tokens * prices["input"] + output_tokens * prices["output"]) / _TOKENS_PER_UNIT


def log_llm_call(
    *,
    node: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
) -> CostEntry:
    """Build the CostEntry for one LLM call. The single choke point for cost tracking.

    ``model`` must be a key in MODEL_COSTS — pass the config model ID, not the model
    string echoed by the API response (which may be a dated snapshot that won't match).
    """
    return {
        "node": node,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": calculate_cost(model, input_tokens=input_tokens, output_tokens=output_tokens),
        "latency_ms": latency_ms,
    }


def _cell(text: str) -> str:
    """Make a string safe for a markdown table cell.

    Escape backslashes and pipes, then collapse every run of whitespace (including CR/LF
    and tabs) to a single space so nothing can break the row onto a new line.
    """
    escaped = text.replace("\\", "\\\\").replace("|", "\\|")
    return " ".join(escaped.split())


def write_cost_row(
    *,
    date: str,
    question: str,
    sub_question_count: int,
    total_cost_usd: float,
    latency_s: float,
    node_count: int,
    path: Path = DEFAULT_COST_DOC,
) -> None:
    """Append one summary row to the cost-breakdown markdown table.

    Assumes ``path`` (the committed docs/cost-breakdown.md, with its header) exists.
    """
    row = (
        f"| {date} "
        f"| {_cell(question)} "
        f"| {sub_question_count} sub-questions "
        f"| ${total_cost_usd:.4f} "
        f"| {latency_s:.1f}s "
        f"| {node_count} nodes |\n"
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(row)


def get_langfuse_client(settings: Settings) -> "Langfuse | None":
    """Return a configured Langfuse client, or None when keys are absent (no-op tracing)."""
    public, secret = settings.langfuse_public_key, settings.langfuse_secret_key
    if not (public and secret):
        if public or secret:
            logger.warning("Langfuse partially configured (one key set) — tracing disabled")
        return None
    import langfuse

    return langfuse.Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
