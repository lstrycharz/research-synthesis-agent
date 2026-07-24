# Progress

<!-- Cross-session handoff. Read this first when resuming. -->

## Completed
- **Chunk 1 — Scaffold** (`99251ad`): uv + Python 3.12, dependency set locked in `uv.lock`.
  Verified current versions (langgraph 1.x, langchain-anthropic 1.x, langfuse **v3**,
  tavily-python, pydantic v2) — the original build spec's pins (langgraph 0.6.x, langfuse 2.x)
  were stale. `src/` + `tests/` skeleton, `.env.example`, `docs/cost-breakdown.md`,
  populated `CLAUDE.md`.
- **Chunk 2 — Config + State** (`65c08da`): `src/state.py` (TypedDicts with operator.add
  reducers on fan-in fields) + `src/config.py` (pydantic-settings, Langfuse-optional).
  11 tests green; code-reviewer findings addressed (hermetic config tests, real validation).
- **Chunk 3 — Observability**: `src/observability.py` — `MODEL_COSTS` (single source of
  truth), `calculate_cost`, `log_llm_call` -> CostEntry, `write_cost_row` (markdown-safe
  cell escaping), `get_langfuse_client` (None without keys, warns on partial config).
  Shared env-isolation fixture moved to `tests/conftest.py`. 21 tests green; reviewer
  findings addressed.

## In Progress
- Nothing mid-flight. Clean stopping point after Chunk 3.

## Blocked
- None.

## Next Up (in order)
1. **Chunk 4 — Searcher** (`src/agents/searcher.py`): Tavily via httpx, 10s timeout,
   retry-once on 429/5xx, empty/error -> populate SearchResult.error, never crash the graph.
   No LLM. Test with mocked Tavily.
2. Chunks 5-11 per plan: summarizer -> supervisor decompose/assemble -> graph wiring ->
   reporter -> CLI + first live run -> README.
3. **When wiring live LLM calls (Chunk 5/10):** validate `settings.supervisor_model` and
   `settings.worker_model` are in `MODEL_COSTS` at pipeline start (fail fast, not mid-run);
   key cost lookups on the *config* model ID, not the API response's (possibly dated) model.

## Known Issues / Notes
- **Cost constants (single source of truth in observability.py):** Haiku 4.5 = $1.00 in /
  $5.00 out per 1M; Sonnet 4.6 = $3.00 / $15.00. (Spec's $0.80/$4.00 for Haiku was outdated.)
- **Langfuse v3 import:** `from langfuse import observe` (NOT `langfuse.decorators`).
  Call `flush()` before process exit or traces are lost.
- Models: supervisor `claude-sonnet-4-6`, workers `claude-haiku-4-5-20251001` (both valid).
- Keys on hand: Anthropic + Tavily. **No Langfuse yet** — sign up (free) before Chunk 10's
  live run. Until then everything is built/tested with mocks; no API spend.
- Pace: user wants **pause & explain after each chunk** (teaching build).

## Session resume protocol
1. Read this file. 2. `git log --oneline -10`. 3. `.claude/verify.sh` (confirm green).
4. Start Chunk 3.
