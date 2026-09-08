---
description: "Use when working on CSV import/parsing logic. Covers delimiter detection, unit parsing, column mapping, and the upsert-by-date rule."
applyTo: "app/services/csv_import.py, tests/test_csv_import.py"
---

# CSV Import Guidelines

- Detect the delimiter (`,`, `;`, `\t`) from the **first data row**, not
  the header — real-world exports have been observed with a
  tab-delimited header but a comma-delimited body.
- Columns are matched by **fixed position** (Énergie, Date, Heures
  Pleines, Heures Creuses, Consommation totale), never by header name —
  the header row is only skipped, never parsed for field names.
- Numeric cells are formatted `"<number> kWh"` — strip the unit before
  casting to `float`; skip (log, don't crash) a row that doesn't match.
- Map source columns to the English model fields: `Heures Pleines` →
  `peak_hours_kwh`, `Heures Creuses` → `off_peak_hours_kwh`,
  `Consommation totale` → `total_kwh`.
- Upsert by `(user_id, date)`: process rows in file order, **last
  occurrence for a date wins** — this covers both re-imports and
  duplicate date ranges within a single file. See
  [docs/03-csv-import.md](../../docs/03-csv-import.md).
- One invalid row must not fail the whole batch (per-row skip counters);
  one failed file must not partially commit (whole-batch transaction).
