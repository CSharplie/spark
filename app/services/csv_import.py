"""CSV import: parsing, validation, and upsert-by-date. See docs/03-csv-import.md."""

import csv
import io
import re
from datetime import UTC, date, datetime

from sqlmodel import Session, select

from app.db.models import ConsumptionRecord, ImportBatch

_KWH_RE = re.compile(r"^\s*([\d.]+)\s*kWh\s*$")
_MISMATCH_TOLERANCE = 0.05
_DELIMITER_CANDIDATES = (",", ";", "\t")


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _detect_delimiter(lines: list[str]) -> str:
    """Prefer the first data row (not the header) for detection: real-world exports have
    been observed with a tab-delimited header but a comma-delimited body."""
    sample = lines[1] if len(lines) > 1 else (lines[0] if lines else "")
    return max(_DELIMITER_CANDIDATES, key=sample.count)


def _parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    match = _KWH_RE.match(value)
    if not match:
        return None
    number = float(match.group(1))
    return number if number >= 0 else None


def _parse_row(row: list[str]) -> tuple[date, float, float, float, bool] | None:
    """Return (date, peak_hours_kwh, off_peak_hours_kwh, total_kwh, mismatch) or None to skip.

    Columns are matched by fixed position (Énergie, Date, Heures Pleines, Heures Creuses,
    Consommation totale) rather than by header name, since the header row isn't reliably
    split by the same delimiter as the data rows (see docs/03-csv-import.md).
    """
    if len(row) < 5:
        return None
    energy, date_str, peak_str, off_peak_str, total_str = row[0], row[1], row[2], row[3], row[4]

    energy = energy.strip()
    if energy and energy != "Électricité":
        return None

    try:
        record_date = datetime.strptime(date_str.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None

    peak = _parse_number(peak_str)
    off_peak = _parse_number(off_peak_str)
    total = _parse_number(total_str)
    if peak is None or off_peak is None or total is None:
        return None

    mismatch = abs(total - (peak + off_peak)) > _MISMATCH_TOLERANCE
    return record_date, peak, off_peak, total, mismatch


def import_csv(session: Session, user_id: int, filename: str, content: bytes) -> ImportBatch:
    """Parse `content` and upsert consumption_record rows for `user_id` in one transaction."""
    try:
        text = _decode(content)
        lines = text.splitlines()
        delimiter = _detect_delimiter(lines)
        all_rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
        rows = all_rows[1:] if all_rows else []  # skip the header row (parsed by position below)
    except (UnicodeDecodeError, csv.Error) as exc:
        batch = ImportBatch(
            user_id=user_id, source_filename=filename, status="failed", error_message=str(exc)
        )
        session.add(batch)
        session.commit()
        session.refresh(batch)
        return batch

    batch = ImportBatch(user_id=user_id, source_filename=filename, row_count=len(rows))
    session.add(batch)
    session.flush()  # assigns batch.id without committing yet

    existing = {
        record.date: record
        for record in session.exec(
            select(ConsumptionRecord).where(ConsumptionRecord.user_id == user_id)
        )
    }

    inserted = updated = skipped = mismatches = 0
    for row in rows:
        parsed = _parse_row(row)
        if parsed is None:
            skipped += 1
            continue

        record_date, peak, off_peak, total, mismatch = parsed
        mismatches += int(mismatch)

        if record_date in existing:
            record = existing[record_date]
            record.peak_hours_kwh = peak
            record.off_peak_hours_kwh = off_peak
            record.total_kwh = total
            record.import_batch_id = batch.id
            record.updated_at = datetime.now(UTC)
            updated += 1
        else:
            record = ConsumptionRecord(
                user_id=user_id,
                import_batch_id=batch.id,
                date=record_date,
                peak_hours_kwh=peak,
                off_peak_hours_kwh=off_peak,
                total_kwh=total,
            )
            session.add(record)
            existing[record_date] = record
            inserted += 1

    batch.inserted_count = inserted
    batch.updated_count = updated
    batch.skipped_count = skipped
    batch.status = "success" if skipped == 0 else "partial"
    if mismatches:
        batch.error_message = (
            f"{mismatches} row(s) had total_kwh inconsistent with peak+off-peak "
            "(kept as provided by the source file)."
        )

    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch
