#!/usr/bin/env bash
#
# verify.sh — this project's deterministic floor.
#
# THE single source of truth for "is this code OK to commit/merge?". Every gate
# runs THIS one script:
#   - the git pre-commit hook (local, on every commit)
#   - the enforce-floor Claude hook (agent can't commit a repo with no floor)
#   - CI (merge-blocking on PRs — see .claude/ci/)
#
# Keeping it in one place means lint/typecheck/test can never drift between
# "what the agent runs" and "what blocks the merge".
#
# Stack handling is deterministic, not inferred:
#   - Node manager comes from the LOCKFILE (pnpm-lock.yaml / yarn.lock / bun.lockb,
#     else npm). Running npm against a pnpm tree resolves wrong → false greens.
#   - Python tools run THROUGH the project env (`uv run` / `poetry run`) so they
#     hit the venv, never a global pytest that collects 0 tests and reports green.
#   - Monorepos opt in explicitly via VERIFY_ROOTS (no magic tree-walking, which
#     wanders into node_modules/.venv):  VERIFY_ROOTS="backend frontend"
#   - A code stack with NO test runner is a hard failure (not just a warning) —
#     accept the gap deliberately with a marker file:  .claude/verify.allow-no-tests
#
# Two tiers, one script (#14) — so the tiers can never drift apart:
#   verify.sh --quick   lint + typecheck only. Run by the pre-commit hook on the
#                       STAGED SNAPSHOT, so granular save-point commits stay fast.
#   verify.sh           the full floor (lint + typecheck + TESTS). Run by the
#                       pre-push hook and CI — the merge gate is always full.
#
# Exit 0 = green (safe). Non-zero = blocked. init-claude auto-detects your stack;
# edit freely for your project.

set -uo pipefail
fail=0
step() { echo ""; echo "→ $*"; }

MODE=full
[ "${1:-}" = "--quick" ] && MODE=quick

# Directories to verify. Default: repo root. Space-separated; opt-in for monorepos.
# NOTE: space-separated, so an individual path containing a space is unsupported
# (it would split into two roots and get skipped with a warning) — W3.
roots=${VERIFY_ROOTS:-.}

# "No tests" is a floor violation, not a default — a repo can otherwise pass the
# gate by simply never having tests (the exact gap the floor exists to close).
# Hard-fail when a code stack has no test runner, UNLESS the gap is accepted
# deliberately and visibly via a marker file (an owned decision, not a silent
# skip). Resolved once here at the repo root, before any per-root `cd`.
ALLOW_NO_TESTS=0
[ -f .claude/verify.allow-no-tests ] && ALLOW_NO_TESTS=1
no_test_floor() { # called when a stack has no tests; warns, and fails unless opted out
  if [ "$ALLOW_NO_TESTS" -eq 1 ]; then
    echo "    (accepted: .claude/verify.allow-no-tests present — passing without a test floor.)"
  else
    echo "    BLOCKED: create .claude/verify.allow-no-tests to accept this gap deliberately."
    fail=1
  fi
}

node_manager() {   # echo the JS package manager for the cwd, from its lockfile
  if   [ -f pnpm-lock.yaml ]; then echo pnpm
  elif [ -f yarn.lock ];      then echo yarn
  elif [ -f bun.lockb ];      then echo bun
  else echo npm
  fi
}

has_script() {     # $1 = npm script name; true if defined in package.json
  # Pass the name via env, not string-interpolated into the JS, so a script name
  # containing a quote can't break the expression or inject code (W4).
  VERIFY_SCRIPT="$1" node -e "process.exit(require('./package.json').scripts?.[process.env.VERIFY_SCRIPT]?0:1)" 2>/dev/null
}

py_runner() {      # echo "uv run" / "poetry run" / "" for the cwd
  if   [ -f uv.lock ]     && command -v uv     >/dev/null 2>&1; then echo "uv run"
  elif [ -f poetry.lock ] && command -v poetry >/dev/null 2>&1; then echo "poetry run"
  else echo ""
  fi
}

# ── Node / TypeScript (cwd has package.json) ────────────────────────────────
verify_node() {
  local pm; pm=$(node_manager)
  step "node ($pm)"
  has_script lint      && { step "lint";      $pm run lint      || fail=1; }
  has_script typecheck && { step "typecheck"; $pm run typecheck || fail=1; }
  # Tests belong to the full tier (pre-push / CI); quick = commit-time speed.
  [ "$MODE" = "quick" ] && return
  if has_script test; then
    step "test"; $pm run test || fail=1
  else
    # Missing-tests is a DECISION, not a default. Surface it loudly so it's owned,
    # not silently skipped (see ~/.claude/rules/qa.md). It does not hard-fail here
    # — the agent rule + init-claude flag force the human decision — but it must
    # never be invisible.
    echo ""
    echo "⚠️  NO 'test' SCRIPT in package.json — this project has no test floor."
    echo "    Wire a test runner or explicitly accept the gap with the user (qa.md)."
    no_test_floor
  fi
}

# ── Python (cwd has pyproject.toml / setup.py / *.py) ───────────────────────
verify_python() {
  local run; run=$(py_runner)
  if [ -n "$run" ]; then
    # Tools live in the project env; let the runner resolve them (don't gate on
    # host $PATH — that's how a global pytest sneaks in and false-greens).
    step "python ($run)"
    step "ruff";   $run ruff check . || fail=1
    step "mypy";   $run mypy .       || fail=1
    if [ "$MODE" != "quick" ]; then
      step "pytest"; $run pytest -q    || fail=1
    fi
  else
    # No uv/poetry lockfile — fall back to host tools, but never go silently green.
    if command -v ruff   >/dev/null 2>&1; then step "ruff";   ruff check . || fail=1; fi
    if command -v mypy   >/dev/null 2>&1; then step "mypy";   mypy . || fail=1; fi
    if [ "$MODE" = "quick" ]; then
      : # tests belong to the full tier
    elif command -v pytest >/dev/null 2>&1; then step "pytest"; pytest -q || fail=1
    else
      echo ""
      echo "⚠️  no uv/poetry lockfile and pytest not on PATH — Python project has no test floor (see qa.md)."
      no_test_floor
    fi
  fi
}

for root in $roots; do
  if [ ! -d "$root" ]; then
    echo "⚠️  VERIFY_ROOTS lists '$root' but it is not a directory — skipping."
    continue
  fi
  [ "$root" = "." ] || step "── root: $root ──"
  (
    cd "$root" || exit 0
    fail=0
    ran_stack=0
    [ -f package.json ] && { verify_node; ran_stack=1; }
    if [ -f pyproject.toml ] || [ -f setup.py ] || ls ./*.py >/dev/null 2>&1; then
      verify_python
      ran_stack=1
    fi
    # A manifest we can't verify must NOT pass silently: enforce-floor gates
    # go/rust/java repos on this script, and running zero checks then exiting 0
    # is a false-green floor — the exact gap this file exists to close (#7).
    if [ "$ran_stack" -eq 0 ]; then
      for m in go.mod Cargo.toml pom.xml build.gradle build.gradle.kts; do
        if [ -f "$m" ]; then
          echo ""
          echo "⚠️  $m detected but verify.sh has no runner for this stack — the floor would run NOTHING."
          echo "    Add your stack's lint/test commands here (mirror verify_node/verify_python)."
          no_test_floor
          break
        fi
      done
    fi
    exit "$fail"
  ) || fail=1
done

# Lint GitHub Actions workflows if present — catch workflow bugs (bad context
# scoping, typos) LOCALLY, before CI does. Optional, like ruff/mypy: run it if
# installed, otherwise say so loudly rather than skip silently.
if ls .github/workflows/*.y*ml >/dev/null 2>&1; then
  if command -v actionlint >/dev/null 2>&1; then
    step "actionlint"; actionlint || fail=1
  else
    echo ""
    echo "ℹ️  .github/workflows present but actionlint not installed — workflows not linted."
    echo "    Install it to catch workflow bugs locally: brew install actionlint"
  fi
fi

echo ""
if [ "$fail" -eq 0 ]; then echo "✅ verify: green"; else echo "❌ verify: failed — fix before committing"; fi
exit "$fail"
