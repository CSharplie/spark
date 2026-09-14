# Spark — Copilot Instructions

Spark is a personal electricity-consumption tracker: FastAPI + SQLite
backend, server-rendered HTMX/ECharts frontend (no separate SPA
build). Full architecture lives in `/docs/` — read the relevant file
before making related changes, don't duplicate it here:

- [docs/01-architecture.md](../docs/01-architecture.md) — stack, security, i18n
- [docs/02-data-model.md](../docs/02-data-model.md) — DB schema
- [docs/03-csv-import.md](../docs/03-csv-import.md) — CSV parsing/import rules
- [docs/04-auth.md](../docs/04-auth.md) — CLI-only account creation, JWT/cookie auth
- [docs/05-api-routes.md](../docs/05-api-routes.md) — routes (pages, HTMX partials, CLI)
- [docs/06-dashboard-views.md](../docs/06-dashboard-views.md) — dashboard/chart mapping
- [docs/07-project-structure.md](../docs/07-project-structure.md) — repo layout, tooling

## Language

Code, identifiers, comments, CLI output, logs, docs and commit messages
are **English-only**. Only the rendered web UI is translated (English
default + French) via the `t()` catalog under `app/i18n/locales/` — never
hardcode user-facing strings in templates, and add new keys to **both**
`en.json` and `fr.json`.

## Build & test

- Dependency management: `uv sync`, `uv add <pkg>`, `uv run <cmd>`.
- Lint/format: `uv run ruff check .` and `uv run ruff format .` before
  finishing any change.
- Tests: `uv run pytest`.
- DB migrations: `uv run alembic revision --autogenerate -m "..."` then
  `uv run alembic upgrade head`.

## Conventions

- No public signup route — accounts are created only via `spark-cli`.
- All DB access goes through SQLModel sessions in `app/db/` — no raw SQL
  strings.
- Every query touching user data must be scoped by the authenticated
  `user_id`.
- CSV import upserts by `(user_id, date)` — last occurrence in the file
  wins, same rule for re-imports.
