---
description: "Use when working on CSV import/parsing or CSV export logic. Covers delimiter detection, unit parsing, column mapping, the upsert-by-date rule and import/export round-trip."
applyTo: "app/services/csv_import.py, app/services/csv_export.py, tests/test_csv_import.py, tests/test_csv_export.py"
---

# CSV Import Guidelines

- Detect the delimiter (`,`, `;`, `\t`) from the **first data row**, not
  the header — real-world exports have been observed with a
  tab-delimited header but a comma-delimited body.
- Columns are matched by **fixed position** (Énergie, Date, Heures
  Pleines, Heures Creuses, Consommation totale), never by header name —
  the header row is only skipped, never parsed for field names.
- Numeric cells are formatted `"<number> kWh"` — strip the unit before
  casting to `float`; a row that doesn't parse is skipped and counted,
  never a crash (note: a cell like `1..2 kWh` currently passes the regex
  and raises on `float()` — known gap, see docs).
- Map source columns to the English model fields: `Heures Pleines` →
  `peak_hours_kwh`, `Heures Creuses` → `off_peak_hours_kwh`,
  `Consommation totale` → `total_kwh`.
- Upsert by `(user_id, date)`: process rows in file order, **last
  occurrence for a date wins** — this covers both re-imports and
  duplicate date ranges within a single file. See
  [docs/03-csv-import.md](../../docs/03-csv-import.md).
- One invalid row must not fail the whole batch (per-row skip counters);
  the batch row and all upserts are committed together at the end. A file
  that can't be decoded/parsed only produces a `failed` batch row.
- Anything after the import (e.g. the temperature download in
  `routers/imports.py`) runs after that commit and must never roll the
  import back.
- Keep `services/csv_export.py` producing a file `import_csv` accepts
  as-is (round-trip is tested).
