---
description: "Use when editing Jinja2 templates, HTMX partials, or translation catalogs. Covers i18n string keys and chart localization."
applyTo: "app/templates/**, app/i18n/**"
---

# Templates & i18n Guidelines

- Never hardcode user-facing text in a template; use `t("key")`, which
  `render()` (`app/core/templates.py`) injects into every template
  context along with `locale`. Always render through `render()`.
- Every new key must be added to **both** `app/i18n/locales/en.json`
  (reference/default) and `fr.json`; a missing French translation falls
  back to English at runtime, but the key must still exist in `en.json`.
  Catalogs load at startup — restart the dev server after editing them.
- ECharts `option` objects are built server-side in
  `app/services/chart_options.py` and receive the request's `t()` (and
  the locale where month names are needed) so titles, legends and series
  names come out already translated — don't localize chart labels on the
  client. (The calendar heatmap still uses ECharts' built-in labels.)
- Partials fetched via HTMX live under `app/templates/partials/` and are
  never linked to directly, only fetched via `hx-get`/`hx-post`.
- Forms that `hx-post` into a partial stay outside the swapped target and
  include the hidden `csrf_token` field.
- Tailwind CSS is prebuilt in `app/static/css/app.css`: only use classes
  that already exist there (grep for them) unless you rebuild it.
- See [docs/06-dashboard-views.md](../../docs/06-dashboard-views.md) for
  which chart maps to which partial.
