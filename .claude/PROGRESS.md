# Progress

<!-- Cross-session handoff. Read this first when resuming. -->

## Completed
- **Chunk 1 — Scaffold** (`99251ad`): uv + Python 3.12, deps locked in `uv.lock`. Verified
  current versions (langgraph 1.x, langchain-anthropic 1.x, **langfuse 4.x**, tavily-python,
  pydantic v2) — the spec's pins (langgraph 0.6.x, langfuse 2.x) were stale.
- **Chunk 2 — Config + State** (`65c08da`): `state.py` TypedDicts (operator.add reducers on
  fan-in fields) + `config.py` (pydantic-settings, Langfuse-optional).
- **Chunk 3 — Observability** (`919aaca`): `MODEL_COSTS` (single source of truth),
  `calculate_cost`, `log_llm_call`, `write_cost_row`, `get_langfuse_client`. Verified LIVE
  via smoke test (US Langfuse region). langchain dep added (`fbd4963`).
- **Chunk 4 — Searcher** (`08a283d`): async Tavily worker, no LLM. `run_tavily_search` core
  (retry-once on 429/5xx, never raises) + `searcher_node` (10s timeout, partial update).
- **Chunk 5 — Summarizer** (`0201caa`): async Haiku worker. `run_summarize` (empty -> free
  note; model error -> degraded note; else invoke + log_llm_call) + `summarizer_node`.
- **Chunk 6 — Supervisor decompose** (`d5c35e4`): `DecomposedQuestion` (3-5), `run_decompose`
  (include_raw for cost; fails fast — essential), `decompose_node`.
- **Chunk 7 — Supervisor assemble** (`f306575`): `AssembledReport`, `run_assemble` (degrades
  on parse failure AND invoke exception — non-essential), `assemble_node` writes
  `report_intro`/`report_conclusion`. Shared `src/agents/_llm.py` extracted; summarizer refactored.
- **Chunk 8 — Graph wiring** (`src/graph.py`): StateGraph, START -> decompose -> conditional
  fan-out (`fan_out_research` -> one `research` Send per sub-question, capped at
  max_sub_questions) -> fan-in -> assemble -> reporter -> END. `research_node` composes
  searcher+summarizer per branch. Minimal `src/report.py` reporter (Chunk 9 enriches).
  `max_sub_questions`/`search_results_per_query` now constrained `ge=1` (empty fan-out would
  dead-end silently). 58 tests. Fan-in verified by test (2 summaries accumulate before assemble).

## In Progress
- Nothing mid-flight. Clean stopping point after Chunk 8. **Full pipeline wired end-to-end.**

## Blocked
- None.

## Next Up (in order)
1. **Chunk 9 — Reporter** (`src/report.py`): enrich the minimal reporter — proper Markdown
   with source attribution per section and a cost-table row via `write_cost_row`. Test the
   Markdown structure (all sections present, sources listed).
2. **Chunk 10 — CLI + first live run** (`src/main.py`): validate `settings.supervisor_model`
   and `settings.worker_model` are in `MODEL_COSTS` at startup (fail fast); call `get_settings()`
   at startup so config errors surface before fan-out; `langfuse.flush()` before exit; build ONE
   Langfuse client at startup and thread it through (replaces per-node construction).
4. **Chunk 11 — README** (portfolio + interview prep: Business Impact, Failure Modes,
   Defend as Engineer/Stakeholder).

## Known Issues / Notes
- **Cost constants** (observability.py, single source of truth): Haiku 4.5 = $1.00/$5.00 per
  1M; Sonnet 4.6 = $3.00/$15.00.
- **Langfuse is v4** (OTEL-based). Import `from langfuse import get_client`; langchain tracing
  via `from langfuse.langchain import CallbackHandler` (needs `langchain` installed). Call
  `flush()` before exit. **This project is US region** — `LANGFUSE_HOST=https://us.cloud.langfuse.com`.
- **All keys present** (.env): Anthropic + Tavily + Langfuse (US). Tests stay hermetic (mocks).
- Models: supervisor `claude-sonnet-4-6`, workers `claude-haiku-4-5-20251001`.
- `ChatAnthropic` needs explicit `api_key=SecretStr(...)` (env-reading unreliable) — done via
  `_llm.build_chat_model`.
- Pace: user wants **pause & explain after each chunk** (teaching build).
- **Prompt caching is INERT** (summarizer): ~80-token system prompt is below Haiku's
  2048-token minimum cacheable prefix, so `cache_control` does nothing; current cost math is
  exactly correct. If ever enabled, extend `calculate_cost` to read `usage["input_token_details"]`
  with per-tier multipliers (read 0.1x, write 1.25x).

## Session resume protocol
1. Read this file. 2. `git log --oneline -10`. 3. `.claude/verify.sh` (confirm green).
4. Start Chunk 8.
