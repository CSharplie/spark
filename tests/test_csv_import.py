"""CSV import service tests (see docs/03-csv-import.md)."""

from datetime import date
from pathlib import Path

from sqlmodel import Session, select

from app.db.models import ConsumptionRecord, ImportBatch
from app.services.csv_import import import_csv

FIXTURES = Path(__file__).parent / "fixtures"


def test_import_sample_csv_counts_and_upserts(session: Session, test_user) -> None:
    content = (FIXTURES / "sample_consumption.csv").read_bytes()

    batch = import_csv(session, test_user.id, "sample_consumption.csv", content)

    assert batch.row_count == 8
    assert batch.inserted_count == 4
    assert batch.updated_count == 1  # the duplicate 03/05/2025 row overwrites the first
    assert batch.skipped_count == 3  # bad number, invalid date, non-electricity row
    assert batch.status == "partial"

    records = session.exec(
        select(ConsumptionRecord).where(ConsumptionRecord.user_id == test_user.id)
    ).all()
    assert len(records) == 4

    duplicate = next(r for r in records if r.date == date(2025, 5, 3))
    # last occurrence in the file wins (the rounded values, not the full-precision ones)
    assert duplicate.peak_hours_kwh == 16.1
    assert duplicate.off_peak_hours_kwh == 15.5
    assert duplicate.total_kwh == 31.6


def test_import_records_total_mismatch_as_warning_not_failure(session: Session, test_user) -> None:
    content = (FIXTURES / "sample_consumption.csv").read_bytes()

    batch = import_csv(session, test_user.id, "sample_consumption.csv", content)

    # 16/10/2024's total_kwh (2.143) doesn't equal peak+off_peak (3.0) — recorded, not rejected
    assert batch.error_message is not None
    assert "total_kwh" in batch.error_message

    record = session.exec(
        select(ConsumptionRecord).where(
            ConsumptionRecord.user_id == test_user.id, ConsumptionRecord.date == date(2024, 10, 16)
        )
    ).one()
    assert record.total_kwh == 2.143


def test_import_detects_semicolon_delimiter(session: Session, test_user) -> None:
    content = (FIXTURES / "sample_semicolon.csv").read_bytes()

    batch = import_csv(session, test_user.id, "sample_semicolon.csv", content)

    assert batch.status == "success"
    assert batch.inserted_count == 2
    assert batch.skipped_count == 0


def test_import_handles_tab_delimited_header_with_comma_body(session: Session, test_user) -> None:
    """Real-world quirk: header is tab-delimited, data rows are comma-delimited."""
    content = (FIXTURES / "sample_mixed_delimiter.csv").read_bytes()

    batch = import_csv(session, test_user.id, "sample_mixed_delimiter.csv", content)

    assert batch.status == "success"
    assert batch.inserted_count == 2
    assert batch.skipped_count == 0

    record = session.exec(
        select(ConsumptionRecord).where(
            ConsumptionRecord.user_id == test_user.id, ConsumptionRecord.date == date(2024, 10, 16)
        )
    ).one()
    assert record.peak_hours_kwh == 2.143
    assert record.off_peak_hours_kwh == 0.857


def test_reimport_upserts_existing_records_across_batches(session: Session, test_user) -> None:
    first = b"\xef\xbb\xbfEnergie,Date,Heures Pleines,Heures Creuses,Consommation totale\n"
    first += "Électricité,01/01/2026,5 kWh,2 kWh,7 kWh\n".encode()
    second = "Énergie,Date,Heures Pleines,Heures Creuses,Consommation totale\n".encode()
    second += "Électricité,01/01/2026,6 kWh,3 kWh,9 kWh\n".encode()

    import_csv(session, test_user.id, "first.csv", first)
    batch2 = import_csv(session, test_user.id, "second.csv", second)

    assert batch2.inserted_count == 0
    assert batch2.updated_count == 1

    record = session.exec(
        select(ConsumptionRecord).where(
            ConsumptionRecord.user_id == test_user.id, ConsumptionRecord.date == date(2026, 1, 1)
        )
    ).one()
    assert record.total_kwh == 9.0


def test_import_unreadable_file_creates_failed_batch(
    session: Session, test_user, monkeypatch
) -> None:
    """A file that raises csv.Error while parsing should record a failed batch, not crash."""
    import csv

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise csv.Error("boom")

    monkeypatch.setattr("app.services.csv_import.csv.reader", _raise)

    batch = import_csv(session, test_user.id, "broken.csv", b"whatever")

    assert batch.status == "failed"
    assert batch.error_message == "boom"
    assert isinstance(batch, ImportBatch)
