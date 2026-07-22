# Research Synthesis Agent

Multi-agent LangGraph pipeline. A supervisor agent decomposes an open-ended question into
sub-questions, dispatches parallel searcher + summarizer workers, then assembles a structured
Markdown report. Every LLM call is cost-tracked; Langfuse traces each call when configured.

> This README is expanded in the final build chunk with usage, a sample report, a cost table,
> Business Impact, Failure Modes, and a "Defend as an Engineer / Defend as a Stakeholder" section.

## Quick start

```bash
uv sync                         # install the locked dependency set
cp .env.example .env            # then fill in your API keys
uv run python -m src.main "your question here"
```

## Development

- Run the floor (lint + typecheck + test): `.claude/verify.sh`
- Tests only: `uv run pytest -q`
