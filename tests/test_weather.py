"""Daily temperature tests (Open-Meteo calls are mocked with httpx.MockTransport)."""

import re
from datetime import date, timedelta

import httpx
import pytest
from httpx import AsyncClient
from sqlmodel import Session, select

from app.core.deps import get_http_client
from app.db.models import ConsumptionRecord, DailyTemperature, ImportBatch, User
from app.services.weather import Location, set_location, sync_temperatures

PARIS = Location(name="Paris, Île-de-France, France", latitude=48.85, longitude=2.35)


def _add_days(session: Session, user_id: int, days: list[date]) -> None:
    batch = ImportBatch(user_id=user_id, source_filename="fixture.csv")
    session.add(batch)
    session.flush()
    for day in days:
        session.add(
            ConsumptionRecord(
                user_id=user_id,
                import_batch_id=batch.id,
                date=day,
                peak_hours_kwh=6.0,
                off_peak_hours_kwh=4.0,
                total_kwh=10.0,
            )
        )
    session.commit()


class FakeOpenMeteo:
    """Answers geocoding and archive requests; `unavailable` days come back as null."""

    def __init__(self, unavailable: set[date] | None = None) -> None:
        self.unavailable = unavailable or set()
        self.archive_down = False
        self.archive_requests: list[httpx.QueryParams] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "geocoding-api.open-meteo.com":
            if request.url.params["name"] == "Nowhere":
                return httpx.Response(200, json={"generationtime_ms": 0.1})
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "name": "Lyon",
                            "admin1": "Auvergne-Rhône-Alpes",
                            "country": "France",
                            "latitude": 45.75,
                            "longitude": 4.85,
                        }
                    ]
                },
            )

        self.archive_requests.append(request.url.params)
        if self.archive_down:
            raise httpx.ConnectError("archive unreachable", request=request)
        start = date.fromisoformat(request.url.params["start_date"])
        end = date.fromisoformat(request.url.params["end_date"])
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]

        def values(offset: float) -> list[float | None]:
            return [None if d in self.unavailable else d.day + offset for d in days]

        return httpx.Response(
            200,
            json={
                "daily": {
                    "time": [d.isoformat() for d in days],
                    "temperature_2m_min": values(0.0),
                    "temperature_2m_max": values(10.0),
                    "temperature_2m_mean": values(5.0),
                }
            },
        )


def _client(fake: FakeOpenMeteo) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(fake))


def test_sync_stores_min_max_avg_for_consumption_days(session: Session, test_user: User) -> None:
    _add_days(session, test_user.id, [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3)])
    set_location(session, test_user, PARIS)
    fake = FakeOpenMeteo(unavailable={date(2025, 1, 3)})

    result = sync_temperatures(session, test_user, _client(fake))

    assert (result.fetched, result.missing) == (2, 1)
    rows = session.exec(select(DailyTemperature).order_by(DailyTemperature.date)).all()
    assert [r.date for r in rows] == [date(2025, 1, 1), date(2025, 1, 2)]
    assert (rows[1].temperature_min_c, rows[1].temperature_max_c, rows[1].temperature_avg_c) == (
        2.0,
        12.0,
        7.0,
    )
    assert fake.archive_requests[0]["latitude"] == "48.85"


def test_sync_only_fetches_missing_days_and_splits_long_ranges(
    session: Session, test_user: User
) -> None:
    _add_days(session, test_user.id, [date(2023, 1, 1), date(2024, 6, 1)])
    set_location(session, test_user, PARIS)
    fake = FakeOpenMeteo()

    sync_temperatures(session, test_user, _client(fake))
    assert len(fake.archive_requests) == 2  # 517 days apart -> one request per range

    result = sync_temperatures(session, test_user, _client(fake))
    assert (result.fetched, result.missing) == (0, 0)
    assert len(fake.archive_requests) == 2


def test_sync_requires_a_city(session: Session, test_user: User) -> None:
    with pytest.raises(ValueError):
        sync_temperatures(session, test_user, _client(FakeOpenMeteo()))


def test_changing_city_drops_previous_temperatures(session: Session, test_user: User) -> None:
    _add_days(session, test_user.id, [date(2025, 1, 1)])
    set_location(session, test_user, PARIS)
    sync_temperatures(session, test_user, _client(FakeOpenMeteo()))

    set_location(session, test_user, Location(name="Lyon", latitude=45.75, longitude=4.85))

    assert session.exec(select(DailyTemperature)).all() == []


async def _login_and_get_csrf(client: AsyncClient) -> str:
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
    settings_page = await client.get("/settings")
    assert settings_page.status_code == 200
    match = re.search(r'name="csrf_token" value="([^"]+)"', settings_page.text)
    assert match
    return match.group(1)


@pytest.fixture
def fake_open_meteo():
    from app.main import app as fastapi_app

    fake = FakeOpenMeteo()
    fastapi_app.dependency_overrides[get_http_client] = lambda: _client(fake)
    yield fake
    fastapi_app.dependency_overrides.pop(get_http_client)


async def test_settings_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/settings", follow_redirects=False)
    assert response.status_code == 303


async def test_set_city_geocodes_saves_and_downloads(
    client: AsyncClient, session: Session, test_user: User, fake_open_meteo: FakeOpenMeteo
) -> None:
    _add_days(session, test_user.id, [date(2025, 1, 1), date(2025, 1, 2)])
    csrf = await _login_and_get_csrf(client)

    response = await client.post("/settings/city", data={"city": "Lyon", "csrf_token": csrf})

    assert response.status_code == 200
    assert "Lyon, Auvergne-Rhône-Alpes, France" in response.text
    session.expire_all()
    user = session.get(User, test_user.id)
    assert (user.latitude, user.longitude) == (45.75, 4.85)
    assert len(session.exec(select(DailyTemperature)).all()) == 2


async def test_set_unknown_city_shows_error(
    client: AsyncClient, test_user: User, fake_open_meteo: FakeOpenMeteo
) -> None:
    csrf = await _login_and_get_csrf(client)

    response = await client.post("/settings/city", data={"city": "Nowhere", "csrf_token": csrf})

    assert response.status_code == 200
    assert "bg-red-50" in response.text
    assert "Nowhere" in response.text


async def test_sync_without_city_shows_error(
    client: AsyncClient, test_user: User, fake_open_meteo: FakeOpenMeteo
) -> None:
    csrf = await _login_and_get_csrf(client)

    response = await client.post("/settings/temperatures/sync", data={"csrf_token": csrf})

    assert "bg-red-50" in response.text
    assert fake_open_meteo.archive_requests == []


async def test_settings_post_rejects_bad_csrf(
    client: AsyncClient, test_user: User, fake_open_meteo: FakeOpenMeteo
) -> None:
    await _login_and_get_csrf(client)

    response = await client.post("/settings/city", data={"city": "Lyon", "csrf_token": "forged"})

    assert response.status_code == 403


_UPLOAD_CSV = (
    "Énergie,Date,Heures Pleines,Heures Creuses,Consommation totale\n"
    "Électricité,01/01/2025,6 kWh,4 kWh,10 kWh\n"
    "Électricité,02/01/2025,6 kWh,4 kWh,10 kWh\n"
).encode()


async def _upload(client: AsyncClient, csrf: str) -> str:
    response = await client.post(
        "/import",
        data={"csrf_token": csrf},
        files={"file": ("data.csv", _UPLOAD_CSV, "text/csv")},
    )
    assert response.status_code == 200
    return response.text


async def test_upload_downloads_temperatures_for_imported_days(
    client: AsyncClient, session: Session, test_user: User, fake_open_meteo: FakeOpenMeteo
) -> None:
    set_location(session, test_user, PARIS)
    csrf = await _login_and_get_csrf(client)

    html = await _upload(client, csrf)

    days = session.exec(select(DailyTemperature.date).order_by(DailyTemperature.date)).all()
    assert days == [date(2025, 1, 1), date(2025, 1, 2)]
    assert "Temperatures: 2 day(s) downloaded" in html


async def test_upload_still_imports_when_weather_service_is_down(
    client: AsyncClient, session: Session, test_user: User, fake_open_meteo: FakeOpenMeteo
) -> None:
    set_location(session, test_user, PARIS)
    fake_open_meteo.archive_down = True
    csrf = await _login_and_get_csrf(client)

    html = await _upload(client, csrf)

    assert "bg-amber-50" in html
    assert len(session.exec(select(ConsumptionRecord)).all()) == 2
    assert session.exec(select(DailyTemperature)).all() == []


async def test_upload_without_city_skips_temperatures(
    client: AsyncClient, session: Session, test_user: User, fake_open_meteo: FakeOpenMeteo
) -> None:
    csrf = await _login_and_get_csrf(client)

    html = await _upload(client, csrf)

    assert 'href="/settings"' in html
    assert fake_open_meteo.archive_requests == []
    assert len(session.exec(select(ConsumptionRecord)).all()) == 2
