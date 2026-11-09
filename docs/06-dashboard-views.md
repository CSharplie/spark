# Dashboard views

Two views, rendered by `app/routers/dashboard.py` and filled in with
HTMX: `/dashboard?year=2026&month=8` (month) and
`/dashboard/annual?year=2026` (year). Their URLs keep the filter state,
so they are bookmarkable. Data comes from `services/aggregation.py`,
`forecast.py` and `energy_signature.py`; ECharts options are built in
`services/chart_options.py`.

Titles, legends, series names and table labels go through `t()` (see
[01-architecture.md](./01-architecture.md#internationalization-i18n)),
and month names through Babel. Numbers use fixed formats (`%.1f`), daily
dates are ISO, and the calendar heatmap uses ECharts' built-in labels.

## Navigation and filters

- **Tabs** "Month" / "Annual" are plain links to `/dashboard` and
  `/dashboard/annual` (the selected year/month isn't carried over).
- **Year selector**: the distinct years present in the user's
  `consumption_record` (descending). Default year/month: those of the
  latest consumption day, or today without data.
- **Month selector** (monthly view only): 1–12.
- Every panel has its own `hx-get` with `hx-include="#dashboard-filters"`
  and `hx-trigger="load, change from:#dashboard-filters"`: panels load in
  parallel and refresh independently when a filter changes. The KPI
  partial returns `HX-Push-Url`, so the address bar follows the filters.
  The page heading (month name / year) is rendered with the page and
  isn't updated by filter changes.

## Monthly view (`/dashboard`)

| Data | Component | Chart type (ECharts) |
|---|---|---|
| KPI cards: total, vs N-1 (kWh and %), peak hours, off-peak hours, daily average, highest day, CO2 | `#kpis` | HTML cards |
| Month summary: median, std deviation, min, max, 30-day average before the month, deviation of the month's daily average vs that average, unusual-day count | `#monthly-summary-table` (sent out-of-band by the KPI partial) | HTML table |
| Month N vs N-1 totals | `#month-comparison` | bar (2 bars) |
| Daily consumption: peak/off-peak, unusual-day markers, average temperature | `#daily-chart` | stacked bars + scatter markers + temperature line on a right-hand °C axis |
| Peak/off-peak split | `#split-pie` | donut |
| Weather & consumption for the month (see [Energy signature](#energy-signature)) | `#weather-summary` | HTML table |
| Energy signature, the month's days highlighted | `#energy-signature` | scatter (kWh/day vs average °C) + fitted model line |

**Unusual day**: its total differs by **more than 50 %** from the mean of
the **30 previous records** (rows, not calendar days; at least 5
required; the day itself excluded). If that mean is ~0, a day is unusual
when it exceeds 1 kWh.

**Temperatures** come from `daily_temperature` (see
[02-data-model.md](./02-data-model.md)). Days without one leave a gap in
the line; if the month has none, the line and the °C axis are omitted.

## Annual view (`/dashboard/annual`)

| Data | Component | Chart type (ECharts) |
|---|---|---|
| KPI cards: total this year, monthly average (over months with data), highest and lowest month | `#kpis` | HTML cards |
| 12 months N vs N-1, forecast stacked on N, monthly average temperature N and N-1 | `#monthly-summary` (top) | bars + 2 temperature lines (N solid, N-1 dashed) on a right-hand °C axis |
| Peak/off-peak split per month (N) | `#monthly-summary` (bottom) | stacked bars |
| Weather & consumption for the year (see [Energy signature](#energy-signature)) | `#weather-summary` | HTML table |
| Energy signature, the year's days highlighted | `#energy-signature` | scatter + fitted model line |
| Cumulative kWh since January, N vs N-1 + forecast | `#cumulative` | lines, dashed for the forecast |
| Seasonal totals, actual vs forecast | `#season-split` | stacked bars |
| kWh/day calendar | `#calendar-heatmap` | ECharts `calendar` + `heatmap` |

- **Monthly average temperature**: mean of the month's daily averages,
  over the days that have one.
- **Seasons** (meteorological): winter = Dec, Jan, Feb; spring = Mar–May;
  summer = Jun–Aug; autumn = Sep–Nov — all within the selected year (so
  "winter" is January, February and December of that year).

### Forecast

`services/forecast.py`, computed on read, never persisted:

1. **Ratio** = kWh of year N up to the cut-off date ÷ kWh of N-1 up to
   the same date (1.0 if N-1 has no data). For the current year the
   cut-off is today, with the day capped at 28; for a past year it is
   31 December.
2. **Months not started yet**: N-1's total for that month × ratio.
3. **Current month**: only its remainder is forecast — (N-1's month total
   − N-1's same month up to the cut-off day) × ratio — so already
   recorded kWh are never counted twice.

A past year has nothing to forecast; a future year forecasts all 12
months. The seasonal forecast is the sum of the monthly forecasts.

## Energy signature

Computed on read by `services/energy_signature.py` from consumption days
that have a temperature; nothing is persisted.

**Model.** Daily consumption is fitted as
`kWh = base + a·HDD + c·CDD`, with `HDD = max(0, Th − Tavg)` and
`CDD = max(0, Tavg − Tc)` (heating/cooling degree-days):

- `base`: weather-independent base load (kWh/day).
- `a`, `c`: kWh per heating/cooling degree-day (cold/heat sensitivity).
- `Th`, `Tc`: balance temperatures below/above which heating/cooling runs.
  They are not fixed: every `Th` in 10–22 °C and `Tc` in 16–28 °C (0.5 °C
  steps, with a neutral band `Tc − Th ≥ 3 °C`) is tried.

**Model selection.** Candidates need positive slopes and at least 10
days beyond each balance temperature. For each structure (heating +
cooling, heating only, cooling only, constant), the lowest-error
candidate is kept; its slopes are then tested (one-sided t-test,
t ≥ 1.65 ≈ 95 %). The structure with the most significant slopes wins
(lowest error on a tie), the constant model being the fallback. So a
household without air conditioning, or a year without hot days, gets
"not detected" for cooling instead of a meaningless slope.

**Robustness.** After a first fit, days under half its base load
(absences, e.g. summer holidays, which would otherwise hide cooling) are
excluded and the model is refitted; then days more than 3 σ off the
model (guests, unusual events) are excluded and it is refitted again.
Each step only applies if at least 60 days remain. The number of
excluded days is shown under the table.

**Window.** The model is fitted on the selected period, extended to at
least 365 days ending at `min(end of the period, latest consumption
day)`, so a single month still gets a signature covering both seasons.
Only days with a temperature count, and at least 60 are required.

**Indicators for the selected period** (`#weather-summary`):

- Estimated heating / cooling kWh and share: `a·ΣHDD`, `c·ΣCDD` over the
  period's days, relative to the modelled total (`base·days + heating +
  cooling`).
- Base load, cold/heat sensitivity with their balance temperatures, R².
- **vs last year at equal weather**: a reference model is fitted the same
  way on the window one year earlier, then used to predict what last
  year's household would have consumed under *this* period's weather:
  `(actual − predicted) / predicted`. Unavailable when that earlier
  window has fewer than 60 usable days.

The chart shows the window's days (grey), the period's days (blue) and
the fitted curve.

## Mobile compatibility

- KPI cards: 2 columns, 4 from the `sm` breakpoint; chart panels: 1
  column, 2 from `lg`.
- ECharts containers are full-width; charts are re-initialized after
  each HTMX swap and resized on window `resize`.
- The calendar heatmap keeps a minimum width of 700 px and scrolls
  horizontally on narrow screens instead of being squashed.
- Filters and form controls are at least 44 px high.