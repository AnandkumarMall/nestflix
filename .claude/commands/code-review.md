---
description: Review the current diff for quality and security before shipping a feature
allowed-tools: Read, Grep, Glob, Bash, Task
---

Review the work on the current feature branch before `/ship-feature`.

## Step 1 — Gather the diff
```bash
git branch --show-current
git diff main...HEAD --stat
git diff main...HEAD
```

## Step 2 — Run reviewers in parallel
Launch both subagents concurrently:
- `nestflix-quality-reviewer` — conventions, simplicity, DRY, dead code
- `nestflix-security-reviewer` — path traversal, injection, secret leakage, SSRF

## Step 3 — Run the tests
Launch `nestflix-test-runner` to confirm the suite passes.

## Step 4 — Synthesize
Print a single consolidated report:
- 🔴 Blockers (must fix before shipping)
- 🟡 Should-fix (recommended)
- 🟢 Nits (optional)
- ✅ Test verdict

Do not modify files in this command — it is review-only. The user decides what to fix.
