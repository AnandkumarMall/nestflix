---
description: Commit, push, open PR, squash-merge, and clean up after a feature is complete
allowed-tools: Read, Bash, mcp__github__create_pull_request, mcp__github__merge_pull_request, mcp__github__update_pull_request
---

Repository: `AnandkumarMall/nestflix` (base branch: `main`).

## Step 1 — Identify current branch
```bash
git branch --show-current
```
Store as CURRENT_BRANCH. If it is `main`, STOP — never ship from main.

## Step 2 — Generate commit message
```bash
git diff --staged
git diff
git log main..HEAD --oneline
```
Read the matching spec in `.claude/specs/`. Generate a Conventional Commit message:
- `feat:` new feature · `fix:` bug fix · `chore:` tooling/config · `docs:` docs only

Rules: lowercase, no trailing period, under 72 chars, describes what the user can now do.
Good: "feat: stream local files with resume from last position"
Bad: "feat: added /stream route and watch_progress table"

## Step 3 — Commit
```bash
git add .
git commit -m "<generated-message>"
```
Report: "✓ Committed — <message>"

## Step 4 — Push the feature branch
```bash
git push -u origin CURRENT_BRANCH
```
Report: "✓ Pushed — CURRENT_BRANCH"

## Step 5 — Create PR via GitHub MCP
Use `mcp__github__create_pull_request` (owner `AnandkumarMall`, repo `nestflix`,
base `main`, head CURRENT_BRANCH).

Title: plain-English feature name (no conventional-commit prefix).
Body:
```markdown
## What this PR does
<one paragraph from the spec Overview>

## Changes
<bullet list of every file changed, one line each>

## Definition of done
<copy the spec's Definition of Done checklist, every item marked [x]>

## How to test
1. <specific steps from the spec to verify this works>
```
Report: "✓ PR created — <PR URL>"

## Step 6 — Merge PR via GitHub MCP
Use `mcp__github__merge_pull_request` with **squash** merge.
Report: "✓ PR merged to main"

## Step 7 — Switch to main, pull, delete branches
```bash
git checkout main
git pull origin main
git push origin --delete CURRENT_BRANCH
git branch -D CURRENT_BRANCH
```
Report: "✓ main up to date · remote + local branch deleted"

## Final summary
```
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
/ship-feature complete
✓ Committed — <message>
✓ Pushed — <branch>
✓ PR created and squash-merged
✓ Remote + local branch deleted
✓ Back on main
Next: run /create-spec for the next feature
╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
```

## Rules
- Never commit directly to main.
- Always squash-merge.
- Always delete both remote and local branch after merge.
- If the GitHub MCP is not connected, STOP and say:
  "GitHub MCP is not connected. Run /mcp to check the connection."
  (Fallback only if the user asks: the same flow works via `gh pr create` / `gh pr merge --squash --delete-branch`.)
- Never proceed to merge if PR creation fails.
