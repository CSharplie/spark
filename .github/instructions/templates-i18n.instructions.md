---
description: "Use when editing Jinja2 templates, HTMX partials, or translation catalogs. Covers i18n string keys and chart localization."
applyTo: "app/templates/**, app/i18n/**"
---

# Templates & i18n Guidelines

- Never hardcode user-facing text in a template; use the `t("key")`
  Jinja2 global.
- Every new key must be added to **both** `app/i18n/locales/en.json`
  (reference/default) and `fr.json`; a missing French translation falls
  back to English at runtime, but the key must still exist in `en.json`.
- ECharts `option` objects are built server-side in `app/services/` and
  must receive the active locale so titles/axis/tooltips come out already
  translated — don't localize chart labels on the client.
- Partials fetched via HTMX live under `app/templates/partials/` and are
  never linked to directly, only fetched via `hx-get`/`hx-post`.
- See [docs/06-dashboard-views.md](../../docs/06-dashboard-views.md) for
  which chart maps to which partial.
