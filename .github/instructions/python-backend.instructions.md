---
description: "Use when writing or editing Python backend code (FastAPI routers, SQLModel models, services, CLI). Covers typing, ORM usage, and English-only code style."
applyTo: "app/**/*.py, tests/**/*.py"
---

# Python Backend Guidelines

- Target Python 3.12+, full type hints on public functions.
- Use SQLModel sessions from `app/db/session.py`; never write raw SQL strings.
- Every query touching `consumption_record` or `import_batch` must filter
  by the authenticated `user_id`.
- Keep aggregation logic (pandas) in `app/services/`, independent of
  FastAPI request/response objects, so it stays unit-testable without an
  HTTP client.
- Identifiers, docstrings, comments and log/CLI messages: English only,
  even though the rendered UI is translated (see
  [docs/01-architecture.md](../../docs/01-architecture.md#internationalization-i18n)).
- Run `uv run ruff check . && uv run ruff format .` before considering a
  change done.
