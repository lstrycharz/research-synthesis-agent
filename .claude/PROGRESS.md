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

## In Progress
- Nothing mid-flight. Clean stopping point after Chunk 2.

## Blocked
- None.

## Next Up (in order)
1. **Chunk 3 — Observability** (`src/observability.py`): `MODEL_COSTS` constants,
   `log_llm_call()`, `write_cost_row()` -> `docs/cost-breakdown.md`, Langfuse client that
   no-ops without keys. Test cost calc to 6 decimals. TDD (red -> green -> review -> commit).
4. Chunks 4-11 per plan: searcher -> summarizer -> supervisor decompose/assemble -> graph
   wiring -> reporter -> CLI + first live run -> README.

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
