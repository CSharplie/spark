"""Dashboard route tests (see docs/05-api-routes.md, docs/06-dashboard-views.md)."""

import json
import re
from datetime import date

from httpx import AsyncClient
from sqlmodel import Session

from app.db.models import ConsumptionRecord, ImportBatch


async def _login(client: AsyncClient) -> None:
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


def _insert_month(session: Session, user_id: int, year: int, month: int) -> None:
    batch = ImportBatch(user_id=user_id, source_filename="fixture.csv")
    session.add(batch)
    session.flush()
    for day in range(1, 6):
        session.add(
            ConsumptionRecord(
                user_id=user_id,
                import_batch_id=batch.id,
                date=date(year, month, day),
                peak_hours_kwh=6.0,
                off_peak_hours_kwh=4.0,
                total_kwh=10.0,
            )
        )
    session.commit()


async def test_dashboard_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


async def test_dashboard_page_renders_with_no_data(client: AsyncClient, test_user) -> None:
    await _login(client)
    response = await client.get("/dashboard")
    assert response.status_code == 200
    assert 'id="dashboard-filters"' in response.text
    assert 'id="kpis"' in response.text
    assert 'id="daily-chart"' in response.text


async def test_kpis_partial_reflects_aggregation(
    client: AsyncClient, session: Session, test_user
) -> None:
    _insert_month(session, test_user.id, 2026, 3)
    await _login(client)

    response = await client.get("/partials/dashboard/kpis", params={"year": 2026, "month": 3})
    assert response.status_code == 200
    assert "50.0 kWh" in response.text  # 5 days * 10 kWh/day


async def test_chart_partials_return_valid_echarts_option(
    client: AsyncClient, session: Session, test_user
) -> None:
    _insert_month(session, test_user.id, 2026, 3)
    await _login(client)

    for path in (
        "/partials/dashboard/daily-chart",
        "/partials/dashboard/split-pie",
        "/partials/dashboard/month-comparison",
    ):
        response = await client.get(path, params={"year": 2026, "month": 3})
        assert response.status_code == 200
        match = re.search(r"data-option='([^']+)'", response.text)
        assert match, f"no chart option found for {path}"
        option = json.loads(match.group(1))
        assert "series" in option


async def test_annual_dashboard_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/dashboard/annual", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


async def test_annual_dashboard_page_renders(client: AsyncClient, test_user) -> None:
    await _login(client)
    response = await client.get("/dashboard/annual")
    assert response.status_code == 200
    assert 'id="dashboard-filters"' in response.text
    assert 'id="kpis"' in response.text
    assert 'id="monthly-summary"' in response.text
    assert 'id="cumulative"' in response.text
    assert 'id="season-split"' in response.text
    assert 'id="calendar-heatmap"' in response.text


async def test_annual_kpis_partial_reflects_aggregation(
    client: AsyncClient, session: Session, test_user
) -> None:
    _insert_month(session, test_user.id, 2026, 3)
    _insert_month(session, test_user.id, 2026, 6)
    await _login(client)

    response = await client.get("/partials/dashboard/kpis", params={"year": 2026})
    assert response.status_code == 200
    assert "100.0 kWh" in response.text  # 2 months * 5 days * 10 kWh/day


async def test_annual_chart_partials_return_valid_echarts_option(
    client: AsyncClient, session: Session, test_user
) -> None:
    _insert_month(session, test_user.id, 2025, 3)
    _insert_month(session, test_user.id, 2026, 3)
    await _login(client)

    for path in (
        "/partials/dashboard/monthly-summary",
        "/partials/dashboard/cumulative",
        "/partials/dashboard/season-split",
        "/partials/dashboard/calendar-heatmap",
    ):
        response = await client.get(path, params={"year": 2026})
        assert response.status_code == 200
        match = re.search(r"data-option='([^']+)'", response.text)
        assert match, f"no chart option found for {path}"
        option = json.loads(match.group(1))
        assert "series" in option
