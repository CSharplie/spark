"""CSV export tests (see docs/03-csv-import.md)."""

import re
from datetime import date

from httpx import AsyncClient
from sqlmodel import Session, select

from app.core.security import hash_password
from app.db.models import ConsumptionRecord, ImportBatch, User
from app.services.csv_export import export_csv
from app.services.csv_import import import_csv


def _add_record(session: Session, user_id: int, day: date, peak: float, off_peak: float) -> None:
    batch = ImportBatch(user_id=user_id, source_filename="fixture.csv")
    session.add(batch)
    session.flush()
    session.add(
        ConsumptionRecord(
            user_id=user_id,
            import_batch_id=batch.id,
            date=day,
            peak_hours_kwh=peak,
            off_peak_hours_kwh=off_peak,
            total_kwh=peak + off_peak,
        )
    )
    session.commit()


def test_export_is_sorted_and_scoped_to_user(session: Session, test_user: User) -> None:
    other = User(username="bob", password_hash=hash_password("another-password"))
    session.add(other)
    session.commit()
    _add_record(session, test_user.id, date(2025, 5, 2), 1.5, 2.25)
    _add_record(session, test_user.id, date(2025, 5, 1), 2.143, 0.857)
    _add_record(session, other.id, date(2025, 5, 1), 9.0, 9.0)

    lines = export_csv(session, test_user.id).decode("utf-8-sig").splitlines()

    assert lines == [
        "Énergie,Date,Heures Pleines,Heures Creuses,Consommation totale",
        "Électricité,01/05/2025,2.143 kWh,0.857 kWh,3.0 kWh",
        "Électricité,02/05/2025,1.5 kWh,2.25 kWh,3.75 kWh",
    ]


def test_export_round_trips_through_import(session: Session, test_user: User) -> None:
    _add_record(session, test_user.id, date(2024, 10, 16), 2.143, 0.857)
    _add_record(session, test_user.id, date(2024, 10, 17), 0.714, 0.286)

    batch = import_csv(session, test_user.id, "export.csv", export_csv(session, test_user.id))

    assert batch.status == "success"
    assert batch.updated_count == 2
    assert batch.inserted_count == 0
    record = session.exec(
        select(ConsumptionRecord).where(
            ConsumptionRecord.user_id == test_user.id, ConsumptionRecord.date == date(2024, 10, 16)
        )
    ).one()
    assert record.peak_hours_kwh == 2.143


async def test_export_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/export", follow_redirects=False)
    assert response.status_code == 303


async def test_export_route_returns_csv_attachment(
    client: AsyncClient, session: Session, test_user: User
) -> None:
    _add_record(session, test_user.id, date(2025, 5, 1), 6.0, 4.0)
    login_page = await client.get("/login")
    match = re.search(r'name="csrf_token" value="([^"]+)"', login_page.text)
    assert match
    await client.post(
        "/login",
        data={
            "username": "alice",
            "password": "correct-horse-battery",
            "csrf_token": match.group(1),
        },
    )

    response = await client.get("/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert "Électricité,01/05/2025,6.0 kWh,4.0 kWh,10.0 kWh" in response.content.decode("utf-8-sig")
