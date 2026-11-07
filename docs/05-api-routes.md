# API / routes

All routes are served by the single FastAPI app. "Page" routes return full
HTML documents; "partial" routes return HTML fragments meant to be swapped
into the page by HTMX (requests carry the `HX-Request: true` header).

## Pages

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/login` | public | Login form |
| POST | `/login` | public | Verify credentials, set session cookie |
| POST | `/logout` | required | Clear session cookie |
| GET | `/` | required | Redirect to `/dashboard` |
| GET | `/dashboard` | required | Monthly dashboard page, query: `year`, `month` (defaults: current) |
| GET | `/dashboard/annual` | required | Annual dashboard page, query: `year` (default: current) |
| GET | `/import` | required | CSV upload page + import history |
| GET | `/export` | required | Download all of the user's consumption records as CSV (import-compatible format) |

## HTMX partials

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/partials/dashboard/kpis` | required | KPI cards (query: `year`, `month`) |
| GET | `/partials/dashboard/daily-chart` | required | Daily peak/off-peak stacked bar + outlier markers (month view) |
| GET | `/partials/dashboard/split-pie` | required | Peak/off-peak split donut/pie |
| GET | `/partials/dashboard/month-comparison` | required | Month N vs N-1 bar |
| GET | `/partials/dashboard/monthly-summary` | required | 12-month bar chart (N vs N-1) + peak/off-peak stacked (annual view) |
| GET | `/partials/dashboard/cumulative` | required | Year-to-date cumulative line + forecast |
| GET | `/partials/dashboard/season-split` | required | Repartition by season bar |
| GET | `/partials/dashboard/calendar-heatmap` | required | Annual kWh/day calendar heatmap |
| POST | `/import` | required (+CSRF) | Upload a CSV file, run import, return summary partial |
| GET | `/partials/import/history` | required | Import batch history table |

Each chart partial returns the HTML container plus the ECharts `option`
JSON needed to (re)render it; a small shared JS snippet (in
`app/static/js/charts.js`) initializes/updates the ECharts instance found
in the swapped fragment (using `htmx:afterSwap`).

## JSON (used internally by the chart-init script, not a public API)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/dashboard/month` | required | Raw aggregated data for a month, JSON |
| GET | `/api/dashboard/annual` | required | Raw aggregated data for a year, JSON |

These exist mainly to keep aggregation logic testable independently of
HTML rendering; they are not intended as a versioned public API for now.

## CLI commands (not HTTP, see [04-auth.md](./04-auth.md))

| Command | Description |
|---|---|
| `spark-cli create-user` | Create a new account |
| `spark-cli list-users` | List accounts |
| `spark-cli deactivate-user` | Disable an account |
| `spark-cli reset-password` | Reset a user's password |
