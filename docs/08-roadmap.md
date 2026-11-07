# Roadmap

Phased plan, each phase should leave the app in a working state.

## Phase 0 — Documentation (this phase)

- [x] Propose stack, confirm choices.
- [x] Write `/docs` architecture.

## Phase 1 — Backend skeleton & auth

- `uv` project init, `ruff` config, base FastAPI app, health check route.
- SQLModel models (`User`, `ImportBatch`, `ConsumptionRecord`) + Alembic
  initial migration.
- Typer CLI: `create-user`, `list-users`.
- Login/logout flow with JWT cookie, protected-route dependency, CSRF
  helper.
- Tests: auth flow, CLI user creation.

## Phase 2 — CSV import

- `services/csv_import.py`: delimiter detection, parsing, validation,
  upsert-by-date logic, per-row skip reporting.
- `/import` page + `POST /import` + `/partials/import/history`.
- Tests against the provided sample CSV, including the duplicate-date
  edge case.

## Phase 3 — Aggregation service

- `services/aggregation.py`: daily/monthly/annual rollups, peak/off-peak
  split, N vs N-1 comparisons, rolling 30-day average, unusual-day
  detection, CO2 estimate.
- `services/forecast.py`: year-end forecast calculation.
- Unit tests with fixture data (no HTTP layer involved).

## Phase 4 — Monthly dashboard

- Templates + Tailwind layout (KPI cards, table).
- ECharts partials: daily stacked bar w/ outlier markers, peak/off-peak
  pie, month vs N-1 bar.
- HTMX wiring for month/year filters, `charts.js` init/update logic.

## Phase 5 — Annual dashboard

- ECharts partials: 12-month bars (N vs N-1, peak/off-peak stacked),
  cumulative line + forecast, season split, calendar heatmap.
- View toggle (monthly ⇄ annual) with URL state.

## Phase 6 — Mobile polish & hardening

- Responsive pass on all breakpoints, touch target sizing, calendar
  heatmap horizontal scroll on small screens.
- Security review pass against [01-architecture.md](./01-architecture.md)
  checklist (rate limiting, CSRF, upload limits).
- README with setup/run instructions.

## Later / not planned yet

- Materialized monthly summary table if aggregation performance becomes
  an issue on large histories.
- Multi-energy support (gas/water) if the need arises.
- [x] Containerized deployment.
