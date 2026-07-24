# Project Instructions

<!-- ⚠️  THIS FILE IS AUTO-POPULATED after the first planning session.
     When you run plan mode for the first time, Claude will fill in
     Tech Stack, Commands, Project Structure, and Rules based on the plan.
     Review and adjust as needed. -->

## Session Start

**Fresh project (no PROGRESS.md):**
Run the full test suite to orient yourself on project scope and current state. Do not proceed if tests are failing unless the task is specifically to fix them.

**Resuming work (PROGRESS.md exists):**
1. Read `.claude/PROGRESS.md` for handoff context
2. Run `git log --oneline -10` to see recent commits
3. Run the full test suite — confirm current state is green
4. Read `tasks/todo.md` and `tasks/lessons.md` if they exist
5. Pick the highest-priority incomplete item from PROGRESS.md
6. Begin work — do not re-implement anything marked as Completed

## Tech Stack
- Python 3.12 (pinned via `.python-version`), managed with **uv** (see `uv.lock`)
- LangGraph 1.x — StateGraph, `Send` fan-out, `Annotated` reducers
- langchain-anthropic 1.x — Claude models via `.with_structured_output()`
- Anthropic: supervisor = `claude-sonnet-4-6`, workers = `claude-haiku-4-5-20251001`
- Tavily (`tavily-python`) for web search; httpx for the HTTP layer
- Langfuse v3 (OpenTelemetry-based) for tracing — **optional**, no-ops without keys
- pydantic v2 + pydantic-settings for typed config; pytest + pytest-asyncio; ruff + mypy

## Commands
- Install: `uv sync`
<!-- Auto-populated from first plan mode session.
     Record the real lint / typecheck / test commands here AND wire them into
     .claude/verify.sh — that one script is the floor every gate runs
     (pre-commit hook, enforce-floor hook, CI).

     verify.sh detects the Node manager from the lockfile and runs Python tools
     through the project env (uv run / poetry run). MONOREPO (Python backend +
     Node frontend in one repo): list each sub-project so both suites run —
       VERIFY_ROOTS="backend frontend" .claude/verify.sh
     Defaults to the repo root. -->
- Run the floor: `.claude/verify.sh`  (monorepo: `VERIFY_ROOTS="backend frontend" .claude/verify.sh`)
- Test: `uv run pytest -q`  ·  Lint: `uv run ruff check .`  ·  Typecheck: `uv run mypy .`
- Run: `uv run python -m src.main "your question here"`
- View traces: https://cloud.langfuse.com (once Langfuse keys are set in `.env`)

## Project Structure
- `src/config.py` — pydantic-settings (API keys, model names, limits)
- `src/state.py` — TypedDict graph state (`ResearchState`, `SearchResult`, `Summary`, `CostEntry`)
- `src/agents/` — `supervisor.py` (decompose + assemble), `searcher.py` (Tavily, no LLM), `summarizer.py` (Haiku)
- `src/graph.py` — StateGraph: Send fan-out, reducer fan-in, conditional routing
- `src/observability.py` — cost math, cost log, optional Langfuse client (single source of cost constants)
- `src/report.py` — final Markdown assembly + cost-row append
- `src/main.py` — CLI entrypoint
- `docs/cost-breakdown.md` — one row appended per run

## Rules
- All LLM calls go through `observability.log_llm_call()` — no bare model calls
- Searcher nodes never call an LLM — Tavily only
- State reducers must be explicitly typed with `Annotated[..., operator.add]`
- Cost constants in `observability.py` are the single source of truth — update there only
- Model IDs live in `src/config.py` — never hardcode a model string elsewhere

## Definition of Done
- Tests written before implementation (red/green/refactor cycle)
- `.claude/verify.sh` passes (lint + typecheck + test) — the deterministic floor
- Types pass
- Tests pass
- No new linting errors
- `code-reviewer` agent run on the diff; findings addressed (per workflow.md chunk loop)
- DB migrations generated if models changed
- No `TODO` or `FIXME` left without a linked issue
- Works locally end-to-end before pushing

## Common Gotchas
- The original build spec targeted a stale stack (langgraph 0.6.x, langfuse 2.x). We are on
  **langgraph 1.x** and **langfuse v3** — verify imports against current docs, not the spec.
- Langfuse v3 import is `from langfuse import observe` (NOT `from langfuse.decorators import observe`).
- Langfuse `flush()` must run before process exit or traces are lost.
- Cost constants: Haiku 4.5 = $1.00/$5.00 per 1M in/out; Sonnet 4.6 = $3.00/$15.00 (spec's
  $0.80/$4.00 for Haiku was outdated).
- LangGraph `Send` node functions receive the full state, not just the sub-question field.
- Tavily free tier: 1000 req/month — mock in tests, use real calls sparingly.
- `ChatAnthropic` did NOT pick up `ANTHROPIC_API_KEY` from env in this setup — pass
  `api_key=settings.anthropic_api_key` explicitly (verified via smoke test).
- Langfuse is region-specific: this project is **US** — `LANGFUSE_HOST=https://us.cloud.langfuse.com`
  (env var is `LANGFUSE_HOST`, not `LANGFUSE_BASE_URL`). Wrong region => 401 Unauthorized.
- Langfuse langchain tracing (`from langfuse.langchain import CallbackHandler`) requires the
  `langchain` package installed, and `CallbackHandler()` uses the global client — only attach
  it when `get_langfuse_client()` returns non-None.

## Core Principles
- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
- **Own Your Mistakes**: When wrong, say so, fix it, add a lesson. No excuses.
- **Context Is King**: Read existing code before writing new code. Match patterns already in the repo.
