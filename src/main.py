"""CLI entrypoint: `python -m src.main "your question"`.

Wires the whole pipeline together for one real run:
  1. Load settings and fail fast if a configured model has no pricing (a run with an
     unpriced model would silently record $0 cost — better to stop at startup).
  2. Build ONE Langfuse client up front — its `flush()` before exit is what actually
     ships the buffered trace (LangGraph's callback batches spans in the background).
  3. Invoke the compiled graph, save the Markdown report under `outputs/`, and append
     one summary row to `docs/cost-breakdown.md`.

The deterministic core (`validate_models`, `build_output_path`, `run_research`) takes its
boundaries — the graph, the clock, the output dirs — as arguments so the suite can drive
it with a fake graph and never touch the network. `main` is the thin shell that supplies
the real ones.
"""

import asyncio
import logging
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from langgraph.graph.state import CompiledStateGraph

from src.config import Settings, get_settings
from src.graph import build_graph
from src.observability import (
    DEFAULT_COST_DOC,
    MODEL_COSTS,
    get_langfuse_client,
    write_cost_row,
)
from src.state import CostEntry

logger = logging.getLogger(__name__)

_RECURSION_LIMIT = 25
_SLUG_MAX = 60
# Anchored to the repo root (like DEFAULT_COST_DOC) so reports land here no matter the CWD.
_OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"


def validate_models(settings: Settings) -> None:
    """Fail fast if a configured model isn't in the pricing table.

    An unpriced model would make ``log_llm_call`` raise inside ``calculate_cost`` mid-run:
    essential decompose aborts the whole run, and a worker's ValueError propagates out of
    its branch and fails the run too. Catching it at startup turns a confusing partial run
    into one clear message.
    """
    unpriced = [
        m for m in (settings.supervisor_model, settings.worker_model) if m not in MODEL_COSTS
    ]
    if unpriced:
        raise ValueError(
            f"Model(s) not in MODEL_COSTS pricing table: {unpriced}. "
            "Add pricing in observability.MODEL_COSTS or fix the model IDs in config."
        )


def _slugify(text: str) -> str:
    """Reduce a question to a filesystem-safe slug (alphanumerics + single dashes)."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:_SLUG_MAX].strip("-") or "report"


def build_output_path(question: str, *, now: datetime, outputs_dir: Path) -> Path:
    """Timestamped, slugified report path — asserted to stay inside ``outputs_dir``."""
    name = f"{now:%Y%m%d-%H%M%S}-{_slugify(question)}.md"
    base = outputs_dir.resolve()
    candidate = (base / name).resolve()
    if not candidate.is_relative_to(base):  # defense in depth; the slug already can't traverse
        raise ValueError(f"refusing to write outside outputs dir: {candidate}")
    return candidate


async def run_research(
    question: str,
    *,
    settings: Settings,
    graph: CompiledStateGraph,
    now: datetime,
    outputs_dir: Path,
    cost_doc: Path,
) -> tuple[Path, dict[str, object]]:
    """Run the graph, save the report, append one cost row. Returns (path, final state)."""
    start = time.perf_counter()
    final = cast(
        "dict[str, object]",
        await graph.ainvoke({"question": question}, config={"recursion_limit": _RECURSION_LIMIT}),
    )
    latency_s = time.perf_counter() - start

    cost_log = cast("list[CostEntry]", final.get("cost_log", []))
    sub_questions = cast("list[str]", final.get("sub_questions", []))

    path = build_output_path(question, now=now, outputs_dir=outputs_dir)
    path.write_text(str(final.get("final_report") or ""), encoding="utf-8")

    # Graph nodes that executed: decompose + research×branches + assemble + reporter.
    # (fan_out caps research branches at max_sub_questions; degraded nodes still count.)
    research_branches = min(len(sub_questions), settings.max_sub_questions)
    write_cost_row(
        date=now.strftime("%Y-%m-%d"),
        question=question,
        sub_question_count=len(sub_questions),
        total_cost_usd=sum(entry["cost_usd"] for entry in cost_log),
        latency_s=latency_s,
        node_count=3 + research_branches,
        path=cost_doc,
    )
    return path, final


def question_from_argv(argv: list[str]) -> str:
    """Join all CLI args into the question (so unquoted multi-word input isn't truncated)."""
    return " ".join(argv[1:]).strip()


async def main(argv: list[str]) -> int:
    """CLI shell: validate config, run one research query, flush traces, print the report."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    question = question_from_argv(argv)
    if not question:
        print('usage: python -m src.main "your research question"', file=sys.stderr)
        return 2

    langfuse_client = None
    try:
        settings = get_settings()  # surfaces missing API keys here, before any fan-out
        validate_models(settings)
        langfuse_client = get_langfuse_client(settings)  # one client; the run's flush handle
        graph = build_graph()
        _OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now(tz=UTC)
        path, final = await run_research(
            question,
            settings=settings,
            graph=graph,
            now=now,
            outputs_dir=_OUTPUTS_DIR,
            cost_doc=DEFAULT_COST_DOC,
        )
    except Exception:
        # Don't leak a traceback to the user; log it server-side, return a clear failure code.
        logger.exception("research run failed")
        print("Error: the research run failed — see the log above for details.", file=sys.stderr)
        return 1
    finally:
        if langfuse_client is not None:
            langfuse_client.flush()  # ship buffered spans before the process exits

    print(str(final.get("final_report") or ""))
    print(f"\nSaved report to {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv)))
