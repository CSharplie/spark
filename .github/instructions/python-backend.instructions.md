---
description: "Use when writing or editing Python backend code (FastAPI routers, SQLModel models, services, CLI, tests). Covers typing, ORM usage, user scoping, CSRF, outbound HTTP and English-only code style."
applyTo: "app/**/*.py, tests/**/*.py"
---

# Python Backend Guidelines

- Target Python 3.13+, full type hints on public functions.
- Use SQLModel sessions from `app/db/session.py` with bound parameters;
  never build SQL from strings (the fixed `PRAGMA`s in `session.py` are
  the only literal SQL).
- Every query touching `import_batch`, `consumption_record` or
  `daily_temperature` must filter by the authenticated `user_id`.
- Keep business logic (pandas aggregations, forecast, energy signature,
  weather, CSV) in `app/services/`, independent of FastAPI
  request/response objects, so it stays unit-testable without an HTTP
  client. Routers stay thin.
- Model changes need an Alembic migration (`alembic revision
  --autogenerate`, then review) — see
  [docs/07-project-structure.md](../../docs/07-project-structure.md#tooling).
- State-changing routes are `POST` and check the CSRF token with
  `verify_csrf(request.cookies.get(CSRF_COOKIE_NAME), csrf_token)`; pages
  that render forms issue it with `generate_csrf_token()` +
  `issue_csrf_cookie()`. See [docs/04-auth.md](../../docs/04-auth.md#csrf).
- Outbound HTTP only via the `get_http_client` dependency (`httpx.Client`).
  Sync `def` routes are fine; in `async def` routes, run blocking calls
  with `run_in_threadpool`. Tests mock it with `httpx.MockTransport`
  through `app.dependency_overrides`.
- Identifiers, docstrings, comments and log/CLI messages: English only,
  even though the rendered UI is translated (see
  [docs/01-architecture.md](../../docs/01-architecture.md#internationalization-i18n)).
- Run `uv run ruff check . && uv run ruff format .` and `uv run pytest`
  before considering a change done.
