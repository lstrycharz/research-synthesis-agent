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
- **Chunk 9 — Reporter** (`src/report.py`): pure enriched reporter — title, exec summary, one
  section per summary with per-section Sources (escaped titles + http/https-allowlisted URLs —
  markdown-injection safe), conclusion, in-report cost table. Duplicate sub-questions merge
  sources. 67 tests.
- **Chunk 10 — CLI + first live run** (`src/main.py`, `dcd3561`/`9735119`): `python -m src.main
  "question"`. Deterministic injectable core — `validate_models` (fail fast if a configured model
  isn't priced), `build_output_path` (timestamped, slugified, traversal-safe under `outputs/`),
  `run_research` (invoke graph -> save report -> append one cost row w/ wall-clock latency).
  Thin `main()` shell: joins multi-word argv, builds ONE Langfuse client as the flush handle,
  wraps the run so errors log + return 1 (no traceback leak), flushes in `finally`. Added
  `claude-sonnet-5` pricing ($2/$10 intro, through 2026-08-31) and switched the default supervisor
  model to it (matches `.env`; the stale `claude-sonnet-4-6` default would've failed validation).
  76 tests. **VERIFIED LIVE**: real run of "How do electric cars work?" -> report in `outputs/`,
  cost row ($0.0322, 5 sub-qs, 8 nodes), Langfuse traces confirmed via API. Graceful degradation
  fired for real (one sub-q got off-topic Tavily hits -> summarizer confidence note, no crash).

## In Progress
- Nothing mid-flight. Clean stopping point after Chunk 10. **Full pipeline built AND verified live.**

## Blocked
- None.

## Next Up (in order)
1. **Chunk 11 — README** (portfolio + interview prep): what it solves, install, run, sample output,
   cost table from 3–5 real runs, plus **Business Impact**, **Failure Modes**, and
   **Defend as Engineer / Defend as Stakeholder** sections (user's explicit additions).

## Known Issues / Notes
- **Cost constants** (observability.py, single source of truth): Haiku 4.5 = $1.00/$5.00 per
  1M; Sonnet 5 = $2.00/$10.00 (INTRODUCTORY through **2026-08-31**, then $3.00/$15.00 — bump
  `MODEL_COSTS` on Sep 1 or supervisor cost logs low). Sonnet 4.6 = $3.00/$15.00 kept for ref.
- **Langfuse per-node construction not yet threaded** (deferred optimization): `main` builds one
  client at startup for the flush handle, but each node's `langfuse_config()` still calls
  `get_langfuse_client()` again. Langfuse v4 registers by public_key so these resolve to the same
  underlying client (verified: traces land, no dupes) — it's wasteful, not wrong. Thread the
  startup client through `_llm.langfuse_config` if this ever matters.
- **Langfuse is v4** (OTEL-based). Import `from langfuse import get_client`; langchain tracing
  via `from langfuse.langchain import CallbackHandler` (needs `langchain` installed). Call
  `flush()` before exit. **This project is US region** — `LANGFUSE_HOST=https://us.cloud.langfuse.com`.
- **All keys present** (.env): Anthropic + Tavily + Langfuse (US). Tests stay hermetic (mocks).
- Models: supervisor `claude-sonnet-5`, workers `claude-haiku-4-5-20251001`.
- `ChatAnthropic` needs explicit `api_key=SecretStr(...)` (env-reading unreliable) — done via
  `_llm.build_chat_model`.
- Pace: user wants **pause & explain after each chunk** (teaching build).
- **Prompt caching is INERT** (summarizer): ~80-token system prompt is below Haiku's
  2048-token minimum cacheable prefix, so `cache_control` does nothing; current cost math is
  exactly correct. If ever enabled, extend `calculate_cost` to read `usage["input_token_details"]`
  with per-tier multipliers (read 0.1x, write 1.25x).

## Session resume protocol
1. Read this file. 2. `git log --oneline -10`. 3. `.claude/verify.sh` (confirm green).
4. Start Chunk 11 (README) — the last chunk.
