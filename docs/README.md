# Spark — Documentation Index

Spark is a personal web app to track home electricity consumption: import CSV
exports (e.g. from a smart meter / supplier portal), and explore interactive,
filterable dashboards (monthly and annual views), inspired by the attached
PDF report.

This documentation is written **before any code**, and should be kept in
sync as the implementation evolves.

## Reading order

1. [01-architecture.md](./01-architecture.md) — tech stack, high-level design, security posture
2. [02-data-model.md](./02-data-model.md) — database schema
3. [03-csv-import.md](./03-csv-import.md) — CSV format, parsing rules, edge cases
4. [04-auth.md](./04-auth.md) — CLI account creation, login flow, session security
5. [05-api-routes.md](./05-api-routes.md) — page routes, HTMX partials, CLI commands
6. [06-dashboard-views.md](./06-dashboard-views.md) — monthly/annual dashboard, charts, filters
7. [07-project-structure.md](./07-project-structure.md) — repo layout, tooling, conventions
8. [08-roadmap.md](./08-roadmap.md) — phased implementation plan

## Non-negotiable constraints (from requirements)

- Backend: Python, SQLite, `uv` (dependency management), `ruff` (lint/format).
- Account creation is **CLI-only** — no public self-registration endpoint.
- CSV upload of consumption data (per the provided sample export).
- Dashboards must be interactive, filterable, with a **monthly view** and an
  **annual view**, and must work well on mobile.
- The web UI must support **English and French**, auto-detected from the
  browser's language, with a manual override.

## Language note

Documentation and code (identifiers, comments, CLI output, logs) are in
**English only** — no exception. The rendered **web UI is multilingual**:
English (reference/default locale) and French, detected from the browser
and overridable by the user. See
[01-architecture.md](./01-architecture.md#internationalization-i18n) for
the approach.
