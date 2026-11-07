"""Daily outdoor temperatures from Open-Meteo, stored per user for their configured city.

See docs/02-data-model.md and docs/01-architecture.md#weather-data.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

import httpx
from sqlmodel import Session, func, select

from app.db.models import ConsumptionRecord, DailyTemperature, User

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_DAILY_VARIABLES = "temperature_2m_min,temperature_2m_max,temperature_2m_mean"
_MAX_DAYS_PER_REQUEST = 366


@dataclass(frozen=True)
class Location:
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class SyncResult:
    fetched: int
    missing: int  # consumption days still without data, e.g. too recent for the archive


def geocode_city(client: httpx.Client, query: str) -> Location | None:
    """Return the best Open-Meteo match for `query`, or None if nothing matches."""
    response = client.get(GEOCODING_URL, params={"name": query, "count": 1, "format": "json"})
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        return None
    best = results[0]
    name = ", ".join(
        part for part in (best.get("name"), best.get("admin1"), best.get("country")) if part
    )
    return Location(name=name, latitude=float(best["latitude"]), longitude=float(best["longitude"]))


def set_location(session: Session, user: User, location: Location) -> None:
    """Save `location` on `user`; temperatures stored for a previous location are dropped."""
    if (user.latitude, user.longitude) != (location.latitude, location.longitude):
        for temperature in session.exec(
            select(DailyTemperature).where(DailyTemperature.user_id == user.id)
        ):
            session.delete(temperature)
    user.city = location.name
    user.latitude = location.latitude
    user.longitude = location.longitude
    session.add(user)
    session.commit()
    session.refresh(user)


def fetch_daily_temperatures(
    client: httpx.Client, latitude: float, longitude: float, start: date, end: date
) -> dict[date, tuple[float, float, float]]:
    """Return {day: (min, max, avg)} in °C; days the archive has no data for yet are omitted."""
    response = client.get(
        ARCHIVE_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": _DAILY_VARIABLES,
            "timezone": "auto",
        },
    )
    response.raise_for_status()
    daily = response.json().get("daily") or {}
    temperatures: dict[date, tuple[float, float, float]] = {}
    for day, t_min, t_max, t_avg in zip(
        daily.get("time", []),
        daily.get("temperature_2m_min", []),
        daily.get("temperature_2m_max", []),
        daily.get("temperature_2m_mean", []),
        strict=True,
    ):
        if t_min is None or t_max is None or t_avg is None:
            continue
        temperatures[date.fromisoformat(day)] = (float(t_min), float(t_max), float(t_avg))
    return temperatures


def _date_ranges(days: list[date]) -> Iterator[tuple[date, date]]:
    """Group sorted `days` into (start, end) ranges spanning at most _MAX_DAYS_PER_REQUEST days."""
    start = end = days[0]
    for day in days[1:]:
        if (day - start).days >= _MAX_DAYS_PER_REQUEST:
            yield start, end
            start = day
        end = day
    yield start, end


def sync_temperatures(session: Session, user: User, client: httpx.Client) -> SyncResult:
    """Fetch and store temperatures for every consumption day of `user` that has none yet."""
    if user.latitude is None or user.longitude is None:
        raise ValueError("User has no city configured")

    consumption_days = set(
        session.exec(select(ConsumptionRecord.date).where(ConsumptionRecord.user_id == user.id))
    )
    known_days = set(
        session.exec(select(DailyTemperature.date).where(DailyTemperature.user_id == user.id))
    )
    missing = sorted(consumption_days - known_days)
    if not missing:
        return SyncResult(fetched=0, missing=0)

    fetched = 0
    for start, end in _date_ranges(missing):
        temperatures = fetch_daily_temperatures(client, user.latitude, user.longitude, start, end)
        for day in missing:
            if start <= day <= end and day in temperatures:
                t_min, t_max, t_avg = temperatures[day]
                session.add(
                    DailyTemperature(
                        user_id=user.id,
                        date=day,
                        temperature_min_c=t_min,
                        temperature_max_c=t_max,
                        temperature_avg_c=t_avg,
                    )
                )
                fetched += 1
        session.commit()  # keep completed ranges if a later request fails

    return SyncResult(fetched=fetched, missing=len(missing) - fetched)


def temperature_coverage(session: Session, user_id: int) -> tuple[int, int]:
    """Return (days with temperature, days with consumption) for `user_id`."""
    consumption_days = session.exec(
        select(func.count(ConsumptionRecord.id)).where(ConsumptionRecord.user_id == user_id)
    ).one()
    temperature_days = session.exec(
        select(func.count(DailyTemperature.id)).where(DailyTemperature.user_id == user_id)
    ).one()
    return temperature_days, consumption_days
