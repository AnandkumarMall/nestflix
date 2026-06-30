# Spec: Phase 1 Foundations: Linting and CI

## Overview

Phase 1 establishes code quality standards and automated testing infrastructure across the full stack. This phase adds:
1. **Python linting (ruff)** — backend code quality checks with PEP 8 enforcement
2. **ESLint + Prettier** — frontend TypeScript/React formatting and linting
3. **Vitest + React Testing Library** — frontend component and unit test framework
4. **GitHub Actions CI pipeline** — automatic build, lint, test, type-check on every push/PR

These foundational tools prevent technical debt early and catch regressions as subsequent phases add features. All subsequent phases depend on this CI infrastructure.

## Depends on

None. This is Phase 1.

## API routes

No new routes.

## Database changes

No database changes.

## Backend modules

No new modules. Changes to existing:
- `backend/main.py` — no changes (CI will run tests)
- `backend/db.py` — no changes
- All route handlers — will pass linting checks

## Frontend

No new pages/components. Changes to existing:
- All files in `frontend/src/` — must pass ESLint + Prettier
- No behavior changes; linting/formatting only

## Files to change / create

**Backend:**
- `requirements.txt` — add `ruff`
- `.python-version` or `pyproject.toml` — ruff configuration
- `pyproject.toml` (new) — ruff config if not present

**Frontend:**
- `frontend/package.json` — add `eslint`, `prettier`, `@typescript-eslint/*`, `eslint-plugin-react-hooks`
- `.eslintrc.json` (new) — ESLint configuration
- `.prettierrc.json` (new) — Prettier configuration
- `.prettierignore` (new) — files Prettier should ignore
- `vitest.config.ts` (new) — Vitest configuration
- `frontend/src/components/__tests__/` (new) — directory for component tests
- `frontend/setupTests.ts` (new) — test setup (e.g., mocks, globals)

**CI/CD:**
- `.github/workflows/ci.yml` (new) — GitHub Actions workflow
- `.github/workflows/` (new directory if not present)

## New dependencies

**Backend (pip):**
- `ruff` — Python linter/formatter

**Frontend (npm):**
- `eslint` — JavaScript/TypeScript linter
- `prettier` — code formatter
- `@typescript-eslint/eslint-plugin` — TypeScript rules
- `@typescript-eslint/parser` — TypeScript parser for ESLint
- `eslint-plugin-react-hooks` — React hooks linting
- `eslint-plugin-react` — React linting rules
- `vitest` — frontend test runner (Vite-native)
- `@vitest/ui` — Vitest UI dashboard
- `@testing-library/react` — React component testing
- `@testing-library/jest-dom` — DOM matchers
- `jsdom` — DOM environment for tests

## Rules for implementation

- All Python code must pass `ruff check` and `ruff format`.
- All TypeScript/React code must pass `eslint` and `prettier --check`.
- No code reformatting in Phase 1; only enforce standards for Phase 2+ work.
- CI must run on every push to any branch and every PR; block merges if CI fails.
- Tests are framework setup only; actual test coverage is Phase 4.
- Do NOT add type-checking (`tsc`) to CI yet — it's verbose and should be separate.

## Definition of done

- [ ] `ruff` is installed and configured; `ruff check backend/` passes
- [ ] `ruff format` formats all Python files without errors
- [ ] ESLint is installed and configured; `npm run lint` passes for frontend
- [ ] Prettier is installed and configured; `npm run format:check` passes for frontend
- [ ] Vitest is installed and configured; `npm test` can run (no tests yet, should pass)
- [ ] GitHub Actions workflow `.github/workflows/ci.yml` runs on every push/PR
- [ ] CI workflow runs: `ruff check`, `ruff format --check`, `npm run lint`, `npm run format:check`, frontend build, backend tests
- [ ] CI blocks PR merge if any check fails
- [ ] Local: `npm run lint` and `npm run format:check` added to frontend `package.json`
- [ ] Local: `make lint` and `make format` added to Makefile or documented for backend (optional; `ruff` can run via pip)
- [ ] All existing code passes linting without changes to logic or behavior
- [ ] README updated with "Development" section: how to run linters locally

## Notes

- **Formatter precedence:** Prettier is opinionated and wins. ESLint should not conflict on formatting.
- **No existing test refactoring:** Phase 1 sets up the framework; actual test coverage is Phase 4.
- **CI must be non-blocking for now:** If any existing code doesn't pass, add it to `.eslintignore` / `.ruffignore` and note in PR that Phase 4 will clean this up.
- **Backend tests:** Use existing pytest setup; CI should run `pytest` as-is.
