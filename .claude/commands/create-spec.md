---
description: Create a spec file and feature branch for the next Nestflix feature
argument-hint: "Step number and feature name e.g. 3 streaming-player"
allowed-tools: Read, Write, Glob, Bash(git:*)
---

You are a senior developer spinning up a new feature for **Nestflix**.
Always follow the rules in CLAUDE.md.

User input: $ARGUMENTS

## Step 1 — Check working directory is clean
Run `git status`. If there are uncommitted, unstaged, or untracked files, stop
immediately and tell the user to commit or stash before proceeding.
DO NOT CONTINUE until the working directory is clean.

## Step 2 — Parse the arguments
From $ARGUMENTS extract:
1. `step_number` — zero-padded to 2 digits: 3 → 03, 11 → 11
2. `feature_title` — human readable Title Case (e.g. "Streaming Player")
3. `feature_slug` — kebab-case, a-z/0-9/-, max 40 chars (e.g. streaming-player)
4. `branch_name` — `feature/<feature_slug>`

If you cannot infer these, ask the user to clarify before proceeding.

## Step 3 — Check branch name is not taken
Run `git branch`. If `branch_name` exists, append `-01`, `-02`, etc.

## Step 4 — Switch to main and pull latest
```
git checkout main
git pull origin main
```

## Step 5 — Create and switch to the feature branch
```
git checkout -b <branch_name>
```

## Step 6 — Research the codebase
Read before writing the spec:
- `CLAUDE.md` — architecture, conventions, constraints
- `backend/main.py` and the relevant `backend/routes/*.py`
- `backend/db.py` and `backend/schema.sql` — existing schema
- The relevant `frontend/src/` pages/components
- All files in `.claude/specs/` — avoid duplicating existing specs

## Step 7 — Write the spec
Generate a spec with this exact structure:

---
# Spec: <feature_title>

## Overview
One paragraph: what this feature does and why it exists at this stage of Nestflix.

## Depends on
Which previous steps this feature requires to be complete.

## API routes
Every new route: `METHOD /path` — description — auth/profile scope.
If none: "No new routes".

## Database changes
New tables/columns/indexes. Verify against `backend/schema.sql` first.
If none: "No database changes".

## Backend modules
Which `backend/` files/functions are created or changed (scanner, tmdb, enrich,
streaming, recommender/*, etc.).

## Frontend
- **Create:** new pages/components with paths under `frontend/src/`
- **Modify:** existing pages/components and what changes
- API calls go through `frontend/src/api/`

## Files to change / create
Explicit lists.

## New dependencies
New pip or npm packages. If none: "No new dependencies".

## Rules for implementation
Always include:
- DB logic in `backend/db.py` / `recommender/` — never in route handlers
- All TMDB access through `backend/tmdb.py`
- Parameterized SQL only
- Frontend calls only through `frontend/src/api/`
- Secrets from `config.py`, never hardcoded

## Definition of done
A specific, testable checklist — each item verifiable by running the app or tests.
---

## Step 8 — Save the spec
Save to: `.claude/specs/<step_number>-<feature_slug>.md`

## Step 9 — Report
```
Branch:    <branch_name>
Spec file: .claude/specs/<step_number>-<feature_slug>.md
Title:     <feature_title>
```
Then tell the user: "Review the spec, then enter Plan Mode (Shift+Tab twice) to begin."
Do not print the full spec in chat unless asked.
