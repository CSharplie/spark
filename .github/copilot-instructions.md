# Spark — Copilot Instructions

Spark is a personal electricity-consumption tracker: FastAPI + SQLite
backend, server-rendered HTMX/ECharts frontend (no SPA, no JSON API),
daily temperatures from Open-Meteo. Full architecture lives in `/docs/` —
read the relevant file before making related changes, keep it up to date
when behavior changes, and don't duplicate it here:

- [docs/01-architecture.md](../docs/01-architecture.md) — stack, i18n, weather data, security
- [docs/02-data-model.md](../docs/02-data-model.md) — DB schema, derived data
- [docs/03-csv-import.md](../docs/03-csv-import.md) — CSV parsing/import rules, export
- [docs/04-auth.md](../docs/04-auth.md) — CLI-only accounts, JWT cookie, CSRF
- [docs/05-api-routes.md](../docs/05-api-routes.md) — routes (pages, HTMX partials, CLI)
- [docs/06-dashboard-views.md](../docs/06-dashboard-views.md) — dashboard panels, forecast, energy signature
- [docs/07-project-structure.md](../docs/07-project-structure.md) — repo layout, tooling, conventions
- [docs/08-docker.md](../docs/08-docker.md) — Docker image, Compose

## Language

Code, identifiers, comments, CLI output, logs, docs and commit messages
are **English-only**. Only the rendered web UI is translated (English
default + French) via the `t()` catalog under `app/i18n/locales/` — never
hardcode user-facing strings in templates, and add new keys to **both**
`en.json` and `fr.json`.

## Build & test

- Dependency management: `uv sync`, `uv add <pkg>`, `uv run <cmd>`.
- Lint/format: `uv run ruff check .` and `uv run ruff format .` before
  finishing any change. Tests: `uv run pytest`. CI doesn't run them.
- Dev server: `uv run spark` (port 8000, reloads on `.py` changes only —
  restart it after editing translation catalogs).
- DB migrations: after changing `app/db/models.py`, run
  `uv run alembic revision --autogenerate -m "..."`, review the script,
  then `uv run alembic upgrade head`. A local DB created by `spark-cli`
  (`create_all`) has no Alembic stamp: `alembic stamp` it first.

## Conventions

- No public signup route — accounts are created only via `spark-cli`.
- All DB access goes through SQLModel sessions in `app/db/` with bound
  parameters — never build SQL from strings.
- Every query on user-owned data (`import_batch`, `consumption_record`,
  `daily_temperature`) is scoped by the authenticated `user_id`.
- Business logic in `app/services/`, routers stay thin; ECharts options
  are built server-side in `app/services/chart_options.py` with `t()`.
- Every state-changing `POST` checks the double-submit CSRF token
  (`verify_csrf`). HTMX forms posting into a partial must stay outside
  the swapped target and must not rotate the token.
- Outbound HTTP only through the `get_http_client` dependency (`httpx`);
  tests mock it with `httpx.MockTransport` — never hit the network in
  tests.
- CSV import upserts by `(user_id, date)` — last occurrence in the file
  wins, same rule for re-imports.
- `app/static/css/app.css` is a prebuilt Tailwind output: only use utility
  classes already present in it (grep first) unless you rebuild it with
  the standalone Tailwind CLI.
