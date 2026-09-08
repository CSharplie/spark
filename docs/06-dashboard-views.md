# Dashboard views

Two top-level views, matching the reference PDF, switchable via a
segmented control (Alpine.js) that swaps the whole dashboard body via
HTMX and updates the URL (`hx-push-url`) so views are bookmarkable/
shareable: `/dashboard?year=2026&month=8` and `/dashboard/annual?year=2026`.

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
- On mobile, filters collapse into a single dropdown/drawer (Alpine
  `x-show`) to keep the header compact.

## Monthly view (`/dashboard`)

Maps to PDF pages 1–2 ("Rapport de consommation électrique" +
"Détail du mois"):

| PDF element | Component | Chart type (ECharts) |
|---|---|---|
| KPI cards (total, vs N-1, HP, HC, daily avg, max day, CO2) | `#kpis` partial | plain HTML cards (no chart) |
| Daily consumption (peak/off-peak split) with "unusual day" markers | `#daily-chart` | stacked bar + scatter overlay for markers |
| Peak/off-peak repartition | `#split-pie` | pie/donut |
| Month N vs N-1 | `#month-comparison` | grouped bar (2 bars) |
| Synthèse du mois (stats table: median, std dev, min/max, 30d avg, unusual days count) | `#monthly-summary-table` | plain HTML table |

"Unusual day" detection (documented for implementation, tunable): a day is
flagged if its total deviates from the trailing 30-day average by more
than a configurable threshold (e.g. ±50%), matching the magnitude implied
by the reference PDF ("Écart vs moyenne 30j −52.7%").

## Annual view (`/dashboard/annual`)

Maps to PDF pages 3–5 ("Consommation mensuelle", "Synthèse annuelle",
"Vue annuelle — kWh/jour"):

| PDF element | Component | Chart type (ECharts) |
|---|---|---|
| Monthly totals, 12 months, N vs N-1 | `#monthly-summary` (top) | grouped bar |
| Peak/off-peak split per month | `#monthly-summary` (bottom) | stacked bar |
| Cumulative kWh since January, N vs N-1 + forecast | `#cumulative` | line chart, dashed segment for the forecast portion |
| Repartition by season (real vs forecast) | `#season-split` | bar, split real/forecast per bar |
| KPI cards (total to date, monthly avg, max/min month) | `#annual-kpis` | plain HTML cards |
| kWh/day calendar heatmap | `#calendar-heatmap` | ECharts `calendar` coordinate system + `heatmap` series |

Forecast method (documented, matches the PDF footnote): apply the current
year's realized daily rate to the previous year's monthly shape to project
the remaining months — computed on the fly by the aggregation service,
never persisted.

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
