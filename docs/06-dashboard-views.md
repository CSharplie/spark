# Dashboard views

Two top-level views are rendered by FastAPI and updated with HTMX. Their URLs
retain filter state so they are bookmarkable: `/dashboard?year=2026&month=8`
and `/dashboard/annual?year=2026`.

All copy and chart labels shown below (titles, axis, tooltips, table
headers) are rendered through the `t()` translation catalog and Babel
locale data (see [01-architecture.md](./01-architecture.md#internationalization-i18n)),
so every panel renders in the active locale (English or French) — the
table below lists the underlying chart type, not a fixed-language label.

## Filters

- **Year selector**: populated from the distinct years present in
  `consumption_record` for the current user.
- **Month selector**: only shown in monthly view; 1–12.
- Changing a filter triggers an HTMX `GET` on all chart partials in
  parallel (each chart panel has its own `hx-get`/`hx-trigger`), so panels
  can refresh independently and show individual loading states.
- On mobile, filters wrap into a compact responsive layout.

## Monthly view (`/dashboard`)

| Data | Component | Chart type (ECharts) |
|---|---|---|
| KPI cards (total, vs N-1, HP, HC, daily avg, max day, CO2) | `#kpis` partial | plain HTML cards (no chart) |
| Daily consumption (peak/off-peak split) with "unusual day" markers, plus daily min/max/avg outdoor temperature | `#daily-chart` | stacked bar + scatter overlay for markers + temperature on a right-hand °C axis (avg: bold line; min/max: thin pale lines forming an envelope) |
| Peak/off-peak repartition | `#split-pie` | pie/donut |
| Month N vs N-1 | `#month-comparison` | grouped bar (2 bars) |
| Synthèse du mois (stats table: median, std dev, min/max, 30d avg, unusual days count) | `#monthly-summary-table` | plain HTML table |

An unusual day is flagged when its total deviates from the trailing 30-day
average beyond the configured threshold.

Temperatures come from `daily_temperature` (see
[02-data-model.md](./02-data-model.md)). The monthly value is the mean of
that month's daily averages over the days that have one. Days/months
without data show as gaps in the line; if the period has no temperature
at all, the temperature series and °C axis are omitted.

## Annual view (`/dashboard/annual`)

| Data | Component | Chart type (ECharts) |
|---|---|---|
| Monthly totals, 12 months, N vs N-1, plus monthly average temperature N vs N-1 | `#monthly-summary` (top) | grouped bar + 2 temperature lines (N solid, N-1 dashed) on a right-hand °C axis |
| Peak/off-peak split per month | `#monthly-summary` (bottom) | stacked bar |
| Cumulative kWh since January, N vs N-1 + forecast | `#cumulative` | line chart, dashed segment for the forecast portion |
| Repartition by season (real vs forecast) | `#season-split` | bar, split real/forecast per bar |
| KPI cards (total to date, monthly avg, max/min month) | `#annual-kpis` | plain HTML cards |
| kWh/day calendar heatmap | `#calendar-heatmap` | ECharts `calendar` coordinate system + `heatmap` series |

The forecast applies the current year's realized daily rate to the previous
year's monthly shape to project the remaining months. It is computed on read
by the aggregation service and is never persisted.

## Mobile compatibility

- Tailwind responsive grid: KPI cards go from a 4-column grid to a
  2-column, then 1-column stack below `sm`/`md` breakpoints.
- ECharts instances are initialized against a container with `width: 100%`
  and re-`resize()`d on window resize / orientation change and on
  `htmx:afterSwap`.
- Chart height is capped and horizontal scroll is used for the calendar
  heatmap on narrow viewports (it has a fixed intrinsic aspect ratio) to
  avoid squashing it unreadably.
- Touch targets (filters, segmented control) sized per mobile guidelines
  (≥44px).
