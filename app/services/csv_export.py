"""CSV export of a user's consumption records, in the same format accepted by the importer.

See docs/03-csv-import.md.
"""

import csv
import io

from sqlmodel import Session, select

from app.db.models import ConsumptionRecord

_HEADER = ("Énergie", "Date", "Heures Pleines", "Heures Creuses", "Consommation totale")
_ENERGY = "Électricité"


def _kwh(value: float) -> str:
    return f"{value} kWh"


def export_csv(session: Session, user_id: int) -> bytes:
    """Return all of `user_id`'s records as a UTF-8 (BOM) CSV that `import_csv` can re-import."""
    records = session.exec(
        select(ConsumptionRecord)
        .where(ConsumptionRecord.user_id == user_id)
        .order_by(ConsumptionRecord.date)
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(_HEADER)
    for record in records:
        writer.writerow(
            (
                _ENERGY,
                record.date.strftime("%d/%m/%Y"),
                _kwh(record.peak_hours_kwh),
                _kwh(record.off_peak_hours_kwh),
                _kwh(record.total_kwh),
            )
        )
    return buffer.getvalue().encode("utf-8-sig")
