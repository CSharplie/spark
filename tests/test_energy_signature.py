"""Energy signature tests on synthetic data with a known heating/cooling response."""

import math
import re
from datetime import date, timedelta

import numpy as np
import pytest
from httpx import AsyncClient
from sqlmodel import Session

from app.db.models import ConsumptionRecord, DailyTemperature, ImportBatch, User
from app.services.energy_signature import DayPoint, analyze_period, fit_signature

BASE, HEATING, COOLING, TH, TC = 10.0, 3.0, 2.0, 16.0, 24.0


def _temperature(day: date, rng: np.random.Generator) -> float:
    seasonal = 13 + 13 * math.sin(2 * math.pi * (day.timetuple().tm_yday - 110) / 365)
    return seasonal + rng.normal(0, 2.5)


def _kwh(temp: float, rng: np.random.Generator, cooling: bool = True) -> float:
    kwh = BASE + HEATING * max(0.0, TH - temp)
    if cooling:
        kwh += COOLING * max(0.0, temp - TC)
    return max(0.1, kwh + rng.normal(0, 1.0))


def _synthetic_days(start: date, n: int, cooling: bool = True, seed: int = 1) -> list[DayPoint]:
    rng = np.random.default_rng(seed)
    days = []
    for i in range(n):
        day = start + timedelta(days=i)
        temp = _temperature(day, rng)
        days.append(DayPoint(date=day, total_kwh=_kwh(temp, rng, cooling), temperature_avg_c=temp))
    return days


def test_fit_recovers_heating_and_cooling() -> None:
    signature = fit_signature(_synthetic_days(date(2025, 1, 1), 365))

    assert signature is not None
    assert signature.base_kwh == pytest.approx(BASE, abs=1.0)
    assert signature.heating_kwh_per_dd == pytest.approx(HEATING, abs=0.3)
    assert signature.heating_balance_c == pytest.approx(TH, abs=1.0)
    assert signature.cooling_kwh_per_dd == pytest.approx(COOLING, abs=0.6)
    assert signature.cooling_balance_c == pytest.approx(TC, abs=1.5)
    assert signature.r2 > 0.9


def test_fit_without_air_conditioning_detects_no_cooling() -> None:
    signature = fit_signature(_synthetic_days(date(2025, 1, 1), 365, cooling=False))

    assert signature is not None
    assert signature.heating_kwh_per_dd is not None
    assert signature.cooling_kwh_per_dd is None
    assert signature.cooling_balance_c is None


def test_fit_ignores_holiday_absences_in_hot_weather() -> None:
    days = _synthetic_days(date(2025, 1, 1), 365)
    holidays = {date(2025, 7, 20) + timedelta(days=i) for i in range(21)}
    days = [DayPoint(d.date, 1.5, d.temperature_avg_c) if d.date in holidays else d for d in days]

    signature = fit_signature(days)

    assert signature is not None
    assert signature.n_days <= 365 - len(holidays)
    assert signature.cooling_kwh_per_dd == pytest.approx(COOLING, abs=0.6)


def test_fit_needs_enough_days() -> None:
    assert fit_signature(_synthetic_days(date(2025, 1, 1), 30)) is None


def _store(session: Session, user_id: int, days: list[DayPoint]) -> None:
    batch = ImportBatch(user_id=user_id, source_filename="synthetic.csv")
    session.add(batch)
    session.flush()
    for d in days:
        session.add(
            ConsumptionRecord(
                user_id=user_id,
                import_batch_id=batch.id,
                date=d.date,
                peak_hours_kwh=d.total_kwh * 0.6,
                off_peak_hours_kwh=d.total_kwh * 0.4,
                total_kwh=d.total_kwh,
            )
        )
        session.add(
            DailyTemperature(
                user_id=user_id,
                date=d.date,
                temperature_min_c=d.temperature_avg_c - 4,
                temperature_max_c=d.temperature_avg_c + 4,
                temperature_avg_c=d.temperature_avg_c,
            )
        )
    session.commit()


def test_analyze_period_splits_consumption_and_corrects_for_weather(
    session: Session, test_user: User
) -> None:
    first_year = _synthetic_days(date(2024, 1, 1), 366, seed=1)
    # Second year: same household using 10 % less, under different weather.
    second_year = [
        DayPoint(d.date, d.total_kwh * 0.9, d.temperature_avg_c)
        for d in _synthetic_days(date(2025, 1, 1), 365, seed=2)
    ]
    _store(session, test_user.id, first_year + second_year)

    year = analyze_period(session, test_user.id, date(2025, 1, 1), date(2025, 12, 31))
    assert year.signature is not None
    assert len(year.period) == 365
    assert year.weather_adjusted_change_pct == pytest.approx(-10, abs=3)
    assert year.heating_share_pct is not None and year.heating_share_pct > 40
    assert year.cooling_kwh > 0

    january = analyze_period(session, test_user.id, date(2025, 1, 1), date(2025, 1, 31))
    assert len(january.period) == 31
    assert january.cooling_kwh == pytest.approx(0, abs=1)
    assert january.heating_kwh > january.base_kwh

    no_history = analyze_period(session, test_user.id, date(2024, 1, 1), date(2024, 12, 31))
    assert no_history.weather_adjusted_change_pct is None


def test_analyze_period_without_temperatures(session: Session, test_user: User) -> None:
    analysis = analyze_period(session, test_user.id, date(2025, 1, 1), date(2025, 12, 31))

    assert analysis.signature is None
    assert analysis.period == []
    assert analysis.weather_adjusted_change_pct is None


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


@pytest.mark.parametrize("query", ["year=2025", "year=2025&month=7"])
async def test_weather_partials_render(
    client: AsyncClient, session: Session, test_user: User, query: str
) -> None:
    _store(session, test_user.id, _synthetic_days(date(2025, 1, 1), 365))
    await _login(client)

    summary = await client.get(f"/partials/dashboard/weather-summary?{query}")
    chart = await client.get(f"/partials/dashboard/energy-signature?{query}")

    assert summary.status_code == 200
    assert "kWh/degree-day" in summary.text
    assert chart.status_code == 200
    assert "scatter" in chart.text


async def test_weather_partials_without_data(client: AsyncClient, test_user: User) -> None:
    await _login(client)

    summary = await client.get("/partials/dashboard/weather-summary?year=2025")
    chart = await client.get("/partials/dashboard/energy-signature?year=2025")

    assert 'href="/settings"' in summary.text
    assert chart.status_code == 200
    assert "scatter" not in chart.text


async def test_weather_partials_require_auth(client: AsyncClient) -> None:
    response = await client.get(
        "/partials/dashboard/weather-summary?year=2025", follow_redirects=False
    )
    assert response.status_code == 303
