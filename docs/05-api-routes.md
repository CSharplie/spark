# Routes

All routes are served by the single FastAPI app (routers in
`app/routers/`). "Page" routes return full HTML documents; "partial"
routes return HTML fragments fetched by HTMX (they don't require the
`HX-Request` header and can be fetched like any `GET`). There is no JSON
API.

Conventions for every route below:

- **Auth "required"**: an active user's `session` cookie (see
  [04-auth.md](./04-auth.md)); otherwise `303 → /login`, for pages and
  partials alike.
- **CSRF**: the `csrf_token` form field must match the `csrf_token`
  cookie; otherwise `403` (`401` for login). See
  [04-auth.md](./04-auth.md#csrf).
- `year` is an integer, `month` an integer from 1 to 12; missing or
  invalid query/form parameters give `422`.

## Pages

| Method | Path | Auth | CSRF | Description |
|---|---|---|---|---|
| GET | `/login` | public | — | Login form; sets the CSRF cookie |
| POST | `/login` | public | yes | Form `username`, `password`, `csrf_token`. Success: `303 → /` + session cookie. Failure: `401` + form with a generic error. Rate-limited or in failed-password cooldown: `429` |
| POST | `/logout` | required | yes | Clears the session cookie, `303 → /login` |
| GET | `/` | required | — | `303 → /dashboard` |
| GET | `/dashboard` | required | — | Monthly dashboard; query `year`, `month` (default: month of the latest consumption day, else today) |
| GET | `/dashboard/annual` | required | — | Annual dashboard; query `year` (same default) |
| GET | `/import` | required | — | CSV upload form + import history |
| POST | `/import` | required | yes | Multipart `file`, `csrf_token`. Runs the import (see [03-csv-import.md](./03-csv-import.md)), then downloads missing temperatures if a city is set. Returns the result partial (summary + history). Bad extension or file > 5 MB: `400` |
| GET | `/export` | required | — | All of the user's records as an import-compatible CSV attachment, `spark-export-YYYY-MM-DD.csv` |
| GET | `/settings` | required | — | City setting, temperature download button, temperature coverage |
| POST | `/settings/city` | required | yes | Form `city` (1–100 chars after trimming): geocode, save, download temperatures. Returns the settings panel partial, with errors (invalid/unknown city, weather service unreachable) shown inside it (`200`) |
| POST | `/settings/temperatures/sync` | required | yes | Download missing temperatures; returns the settings panel partial (error shown inside if no city or service unreachable) |

Pages that render forms (`/login`, `/dashboard`, `/dashboard/annual`,
`/import`, `/settings`) also set a fresh CSRF cookie.

## HTMX partials

All `GET`, auth required, no CSRF.

| Path | Query | Returns |
|---|---|---|
| `/partials/dashboard/kpis` | `year`, `month?` | With `month`: monthly KPI cards + the "month summary" table (swapped out-of-band into `#monthly-summary-table`). Without: annual KPI cards. Sets `HX-Push-Url` to the matching page URL |
| `/partials/dashboard/daily-chart` | `year`, `month` | Daily peak/off-peak stacked bars, unusual-day markers, average temperature line |
| `/partials/dashboard/split-pie` | `year`, `month` | Peak/off-peak donut |
| `/partials/dashboard/month-comparison` | `year`, `month` | Month N vs N-1 bars |
| `/partials/dashboard/monthly-summary` | `year` | 12-month N vs N-1 bars + forecast + monthly average temperatures; peak/off-peak bars below |
| `/partials/dashboard/cumulative` | `year` | Cumulative N vs N-1 lines + forecast |
| `/partials/dashboard/season-split` | `year` | Seasonal totals, actual vs forecast |
| `/partials/dashboard/calendar-heatmap` | `year` | kWh/day calendar heatmap |
| `/partials/dashboard/weather-summary` | `year`, `month?` | "Weather & consumption" table for the month (or year), or a "not enough data" message |
| `/partials/dashboard/energy-signature` | `year`, `month?` | Energy signature scatter + fitted model (or a "not enough data" title) |
| `/partials/import/history` | — | Import history table |

Chart partials return a `<div class="echart" data-option='…'>` holding the
ECharts `option` JSON built server-side (`app/services/chart_options.py`);
`app/static/js/charts.js` initializes the charts found in the page on
load and in each swapped fragment (`htmx:afterSwap`), and resizes them
on window resize. See [06-dashboard-views.md](./06-dashboard-views.md).

## Other

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/healthz` | public | `{"status": "ok"}` — used by the Docker healthcheck (doesn't touch the database) |
| GET | `/static/...` | public | CSS, JS and vendored libraries from `app/static/` |
| GET | `/docs`, `/redoc`, `/openapi.json` | public | FastAPI's interactive docs — **disabled in production** |

## CLI commands (not HTTP, see [04-auth.md](./04-auth.md))

| Command | Description |
|---|---|
| `spark-cli create-user [--username] [--password]` | Create a new account (prompts for missing values) |
| `spark-cli list-users` | List accounts (id, username, active state, creation date) |
| `spark-cli deactivate-user --username` | Disable an account |
| `spark-cli reset-password --username [--password]` | Reset a user's password |
