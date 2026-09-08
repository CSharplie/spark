# Project structure & tooling

## Repository layout

```
spark/
├── docs/                      # this documentation
├── pyproject.toml             # uv-managed, single backend project
├── uv.lock
├── ruff.toml
├── alembic.ini
├── alembic/
│   └── versions/
├── app/
│   ├── main.py                # FastAPI app factory, mounts routers + static
│   ├── core/
│   │   ├── config.py          # pydantic-settings (env vars: JWT secret, CO2 factor, db path)
│   │   └── security.py        # password hashing, JWT encode/decode, CSRF helpers
│   ├── db/
│   │   ├── session.py         # SQLModel engine/session
│   │   └── models.py          # User, ImportBatch, ConsumptionRecord
│   ├── cli/
│   │   └── main.py            # Typer app: create-user, list-users, ...
│   ├── i18n/
│   │   ├── locales/
│   │   │   ├── en.json        # reference/default locale
│   │   │   └── fr.json
│   │   └── middleware.py      # Accept-Language negotiation + locale cookie override
│   ├── routers/
│   │   ├── auth.py
│   │   ├── dashboard.py
│   │   └── imports.py
│   ├── services/
│   │   ├── csv_import.py      # parsing + upsert logic
│   │   ├── aggregation.py     # pandas-based monthly/annual aggregations
│   │   └── forecast.py        # year-end forecast calculation
│   ├── templates/
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── dashboard/
│   │   │   ├── month.html
│   │   │   └── annual.html
│   │   └── partials/          # HTMX fragments (one per chart/panel)
│   └── static/
│       ├── css/               # Tailwind output (built, not hand-edited)
│       ├── js/
│       │   └── charts.js      # ECharts init/update on htmx:afterSwap
│       └── vendor/            # htmx.min.js, alpinejs.min.js, echarts.min.js (self-hosted)
├── tests/
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_csv_import.py
│   └── test_aggregation.py
├── bin/
│   └── tailwindcss            # standalone Tailwind CLI binary (gitignored, not committed)
└── styles/
    └── input.css               # Tailwind v4 source (`@import "tailwindcss";`), compiled via the CLI
```

## Tooling

- **Dependency management**: `uv` — `uv sync`, `uv run <cmd>`, `uv add <pkg>`.
- **Lint/format**: `ruff check .` and `ruff format .`; configured in
  `ruff.toml` (line length, target Python version).
- **DB migrations**: `alembic revision --autogenerate` / `alembic upgrade head`.
- **Localization**: `Babel` for locale-aware date/number/month-name
  formatting; UI strings live in `app/i18n/locales/{en,fr}.json` — add a
  key to **both** files whenever new UI copy is introduced (English is
  the reference, missing French falls back to English at runtime rather
  than failing).
- **CSS build**: Tailwind v4 **standalone CLI binary** (no Node/npm) —
  `./bin/tailwindcss -i styles/input.css -o app/static/css/app.css --minify`.
  Tailwind v4 is CSS-first: there is no `tailwind.config.js`; `styles/input.css`
  just has `@import "tailwindcss";` and the CLI auto-scans the repo (including
  `app/templates/**/*.html`) for classes in use. This is a deliberate choice to
  keep the whole toolchain Python-only, per the "single project, no separate
  frontend build" decision.
- **Tests**: `uv run pytest`, using a temporary SQLite file (or
  in-memory) per test session, `httpx.AsyncClient` against the FastAPI
  app for route-level tests.
- **Entry points** (declared in `pyproject.toml`):
  - `spark` → `uvicorn app.main:app` wrapper / dev server
  - `spark-cli` → `app.cli.main:app` (Typer)

## Conventions

- All DB access goes through `app/db` (SQLModel sessions); no raw SQL
  strings.
- All routes that render HTML use Jinja2 templates under
  `app/templates/`; HTMX partials live under `templates/partials/` and are
  never linked to directly by users (only fetched via `hx-get`).
- Configuration is centralized in `app/core/config.py`, read from
  environment variables / `.env` (never hardcoded secrets).
- One aggregation function per chart, in `app/services/aggregation.py`,
  unit-tested independently of the HTTP layer.
