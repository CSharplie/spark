# Project structure & tooling

## Repository layout

```
spark/
├── docs/                         # this documentation
├── pyproject.toml                # uv project: dependencies, entry points, pytest config
├── uv.lock
├── ruff.toml
├── .python-version               # 3.13
├── .env.example                  # template for the git-ignored .env
├── Dockerfile, .dockerignore, compose.yaml   # see 08-docker.md
├── alembic.ini
├── alembic/
│   ├── env.py                    # DB URL from Settings, SQLModel metadata
│   └── versions/                 # 7b5d93897dc2 initial schema, cba1c3d1741a location + temperatures
├── .github/
│   ├── copilot-instructions.md   # + instructions/*.instructions.md (Copilot guidance)
│   └── workflows/docker-publish.yml
├── app/
│   ├── main.py                   # FastAPI `app`: middlewares, security headers, routers, static, /healthz
│   ├── core/
│   │   ├── config.py             # Settings (pydantic-settings, SPARK_* env vars / .env)
│   │   ├── deps.py               # get_current_user, get_http_client
│   │   ├── exceptions.py         # NotAuthenticated (→ 303 /login)
│   │   ├── rate_limit.py         # in-memory login rate limiter
│   │   ├── security.py           # Argon2 hashing, JWT, CSRF and cookie helpers
│   │   └── templates.py          # Jinja2 environment + render() (injects t, locale)
│   ├── db/
│   │   ├── session.py            # engine (WAL, foreign keys), get_session, init_db
│   │   └── models.py             # User, ImportBatch, ConsumptionRecord, DailyTemperature
│   ├── cli/
│   │   └── main.py               # Typer app: create-user, list-users, deactivate-user, reset-password
│   ├── i18n/
│   │   ├── __init__.py           # catalogs + get_translator
│   │   ├── middleware.py         # Accept-Language negotiation
│   │   └── locales/{en,fr}.json  # en = reference/default
│   ├── routers/
│   │   ├── auth.py               # login, logout, /
│   │   ├── dashboard.py          # dashboard pages + chart/KPI partials
│   │   ├── imports.py            # CSV upload, history, export
│   │   └── settings.py           # city setting + temperature download
│   ├── services/                 # business logic, independent of FastAPI request objects
│   │   ├── csv_import.py         # parsing + upsert
│   │   ├── csv_export.py         # import-compatible CSV export
│   │   ├── aggregation.py        # pandas rollups for both dashboards
│   │   ├── forecast.py           # year-end forecast
│   │   ├── energy_signature.py   # kWh vs temperature model (numpy)
│   │   ├── weather.py            # Open-Meteo geocoding + daily temperatures (httpx)
│   │   └── chart_options.py      # ECharts option dicts, localized via t()
│   ├── templates/
│   │   ├── base.html, login.html, import.html, settings.html
│   │   ├── dashboard/{month,annual}.html
│   │   └── partials/             # HTMX fragments: import result/history, settings panel,
│   │       └── dashboard/        #   KPI cards, tabs, weather summary, echart container
│   └── static/
│       ├── css/app.css           # compiled Tailwind output (committed, not hand-edited)
│       ├── js/charts.js          # ECharts init after load / htmx:afterSwap, resize
│       └── vendor/               # htmx.min.js, echarts.min.js (self-hosted)
├── styles/
│   └── input.css                 # Tailwind v4 source (`@import "tailwindcss";`)
├── tests/
│   ├── conftest.py               # temp SQLite DB per test, test user, AsyncClient
│   ├── test_auth.py, test_cli.py, test_dashboard.py, test_aggregation.py,
│   ├── test_csv_import.py, test_csv_export.py, test_weather.py, test_energy_signature.py
│   └── fixtures/                 # sample CSV exports (comma, semicolon, mixed delimiters)
├── bin/                          # standalone Tailwind CLI, downloaded locally (git-ignored)
└── data/                         # local SQLite database (git-ignored)
```

## Tooling

- **Dependency management**: `uv` — `uv sync`, `uv run <cmd>`, `uv add <pkg>`.
- **Lint/format**: `uv run ruff check .` and `uv run ruff format .`,
  configured in `ruff.toml`: Python 3.13, line length 100, rules
  `E, F, W, I, B, UP, SIM` (`B008` ignored for FastAPI `Depends`), double
  quotes, `alembic/versions` excluded.
- **Tests**: `uv run pytest` (`asyncio_mode = "auto"`). Each test gets a
  fresh temporary SQLite file; route tests use `httpx.AsyncClient` with
  `ASGITransport` against the app. External HTTP (Open-Meteo) is mocked
  with `httpx.MockTransport` by overriding `get_http_client`.
- **DB migrations**: after changing `app/db/models.py`,
  `uv run alembic revision --autogenerate -m "..."`, review the script,
  then `uv run alembic upgrade head`. The Docker image runs
  `alembic upgrade head` on start.
- **Localization**: UI strings live in `app/i18n/locales/{en,fr}.json` —
  add every new key to **both** files (English is the reference; a
  missing French string falls back to English at runtime). Catalogs are
  loaded at startup: restart the dev server after editing them.
- **CSS build**: Tailwind v4 **standalone CLI binary** (no Node/npm). It is
  not part of the repository: download it into `bin/` (git-ignored), then
  `./bin/tailwindcss -i styles/input.css -o app/static/css/app.css --minify`.
  There's no `tailwind.config.js`; the CLI scans the repo (including
  `app/templates/**/*.html`) for classes in use. Until `app.css` is
  rebuilt, only classes already present in it work — check before using
  a new utility class.
- **Entry points** (declared in `pyproject.toml`):
  - `spark` → `app.main:run`, the dev server (Uvicorn, port 8000, auto-reload)
  - `spark-cli` → `app.cli.main:app` (Typer)
- **CI**: `.github/workflows/docker-publish.yml` builds and pushes the
  Docker image to GHCR on pushes to `main`, `v*` tags and manual runs. It
  doesn't run lint or tests — run them locally before pushing.

## Conventions

- Code, identifiers, comments, logs, CLI output and docs are
  English-only; only the web UI is translated.
- All DB access goes through SQLModel sessions (`app/db`), with
  parameterized queries; no SQL built from strings (the fixed `PRAGMA`s in
  `session.py` are the only literal SQL).
- Every query on user-owned data (`import_batch`, `consumption_record`,
  `daily_temperature`) filters by the authenticated `user_id`.
- Business logic lives in `app/services/`, unit-testable without HTTP;
  routers stay thin. Chart options are built server-side in
  `chart_options.py`.
- All application HTML is rendered from Jinja2 templates via
  `render()`; HTMX partials live under `templates/partials/` and are only
  fetched via `hx-get`/`hx-post`, never linked directly.
- Configuration is centralized in `app/core/config.py`, read from
  `SPARK_*` environment variables / `.env` (never hardcoded secrets).
