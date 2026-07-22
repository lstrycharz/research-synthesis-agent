# Make the floor merge-blocking (manual, one-time)

CI runs `.claude/verify.sh` on every PR, but **a red check doesn't block a merge
until you turn on branch protection.** The repo can ship the pipeline; only you
can enable the gate in the host's settings. Do this once per repo.

## GitHub
Settings → Branches → Add branch ruleset (or protect `main`/`develop`/`release`):
- ✅ Require a pull request before merging
- ✅ Require status checks to pass → select **`verify`**
- ✅ Require branches to be up to date before merging
- (recommended) ✅ Require approvals: 1
- (recommended) ✅ Require review from Code Owners (add a `CODEOWNERS` file)

## Bitbucket
Repository settings → Branch restrictions → Add for `main`/`develop`/`release`:
- ✅ Require a minimum number of approvals: 1
- ✅ Check for "successful builds" (the `verify` pipeline) before merging
- ✅ Prevent merging unless all PR checks pass

## Why this matters
Without it, the floor is advisory — someone can merge red. The whole point of a
deterministic floor is that the machine refuses, not that people remember. This
checkbox is the difference.
