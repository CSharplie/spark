"""Daily/monthly/annual rollups, peak/off-peak split, N vs N-1, unusual-day
detection, and CO2 estimate — computed on the fly, nothing persisted.

See docs/02-data-model.md#derived-data and docs/06-dashboard-views.md.
"""

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from sqlmodel import Session, select

from app.core.config import get_settings
from app.db.models import ConsumptionRecord, DailyTemperature

ROLLING_WINDOW_DAYS = 30
MIN_ROLLING_PERIODS = 5
UNUSUAL_DAY_RELATIVE_THRESHOLD = 0.5  # ±50% vs the trailing 30-day average

SEASON_MONTHS: dict[str, set[int]] = {
    "winter": {12, 1, 2},
    "spring": {3, 4, 5},
    "summer": {6, 7, 8},
    "autumn": {9, 10, 11},
}


@dataclass
class DailyPoint:
    date: date
    peak_hours_kwh: float
    off_peak_hours_kwh: float
    total_kwh: float
    is_unusual: bool
    temperature_avg_c: float | None = None


@dataclass
class MonthSummary:
    year: int
    month: int
    total_kwh: float
    peak_hours_kwh: float
    off_peak_hours_kwh: float
    peak_pct: float
    off_peak_pct: float
    daily_avg_kwh: float
    max_day: DailyPoint | None
    co2_kg: float
    previous_year_total_kwh: float | None
    delta_kwh: float | None
    delta_pct: float | None
    median_kwh: float
    stdev_kwh: float
    min_kwh: float
    max_kwh: float
    rolling_30d_avg_kwh: float | None
    rolling_30d_delta_pct: float | None
    unusual_day_count: int
    daily_points: list[DailyPoint] = field(default_factory=list)


@dataclass
class MonthlyTotal:
    month: int
    total_kwh: float
    peak_hours_kwh: float
    off_peak_hours_kwh: float
    temperature_avg_c: float | None = None  # mean of the month's daily averages


@dataclass
class AnnualSummary:
    year: int
    months_current: list[MonthlyTotal]
    months_previous: list[MonthlyTotal]
    total_to_date_kwh: float
    monthly_avg_kwh: float
    max_month: MonthlyTotal | None
    min_month: MonthlyTotal | None
    season_totals: dict[str, float]
    calendar: dict[date, float]


def load_dataframe(session: Session, user_id: int) -> pd.DataFrame:
    """All of `user_id`'s daily records as a DataFrame indexed by date, sorted ascending."""
    records = session.exec(
        select(ConsumptionRecord)
        .where(ConsumptionRecord.user_id == user_id)
        .order_by(ConsumptionRecord.date)
    ).all()

    columns = ["peak_hours_kwh", "off_peak_hours_kwh", "total_kwh"]
    if not records:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], name="date"))

    df = pd.DataFrame(
        [
            {
                "date": r.date,
                "peak_hours_kwh": r.peak_hours_kwh,
                "off_peak_hours_kwh": r.off_peak_hours_kwh,
                "total_kwh": r.total_kwh,
            }
            for r in records
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def load_temperatures(
    session: Session, user_id: int, start: date, end: date
) -> dict[date, DailyTemperature]:
    """`user_id`'s stored daily temperatures between `start` and `end` (inclusive), by date."""
    rows = session.exec(
        select(DailyTemperature).where(
            DailyTemperature.user_id == user_id,
            DailyTemperature.date >= start,
            DailyTemperature.date <= end,
        )
    )
    return {row.date: row for row in rows}


def _apply_monthly_temperatures(
    months: list[MonthlyTotal], temperatures: dict[date, DailyTemperature], year: int
) -> None:
    for m in months:
        values = [
            t.temperature_avg_c
            for day, t in temperatures.items()
            if day.year == year and day.month == m.month
        ]
        m.temperature_avg_c = sum(values) / len(values) if values else None


def _is_unusual(value: float, trailing_avg: float | None) -> bool:
    if trailing_avg is None or pd.isna(trailing_avg):
        return False
    if trailing_avg <= 1e-6:
        return value > 1.0  # baseline ~0: only flag a clearly non-trivial day
    return abs(value - trailing_avg) / trailing_avg > UNUSUAL_DAY_RELATIVE_THRESHOLD


def monthly_totals(df: pd.DataFrame, year: int) -> list[MonthlyTotal]:
    year_df = df[df.index.year == year] if not df.empty else df
    return [
        MonthlyTotal(
            month=month,
            total_kwh=(m := year_df[year_df.index.month == month])["total_kwh"].sum(),
            peak_hours_kwh=m["peak_hours_kwh"].sum(),
            off_peak_hours_kwh=m["off_peak_hours_kwh"].sum(),
        )
        for month in range(1, 13)
    ]


def get_month_summary(session: Session, user_id: int, year: int, month: int) -> MonthSummary:
    df = load_dataframe(session, user_id)
    settings = get_settings()

    # Trailing (not centered) 30-day average, excluding the current day itself.
    trailing_avg = (
        df["total_kwh"]
        .rolling(window=ROLLING_WINDOW_DAYS, min_periods=MIN_ROLLING_PERIODS)
        .mean()
        .shift(1)
        if not df.empty
        else pd.Series(dtype=float)
    )

    month_df = df[(df.index.year == year) & (df.index.month == month)] if not df.empty else df
    month_start_day = date(year, month, 1)
    month_end_day = date(year, month, monthrange(year, month)[1])
    temperatures = load_temperatures(session, user_id, month_start_day, month_end_day)

    daily_points: list[DailyPoint] = []
    for idx, row in month_df.iterrows():
        temperature = temperatures.get(idx.date())
        daily_points.append(
            DailyPoint(
                date=idx.date(),
                peak_hours_kwh=row["peak_hours_kwh"],
                off_peak_hours_kwh=row["off_peak_hours_kwh"],
                total_kwh=row["total_kwh"],
                is_unusual=_is_unusual(row["total_kwh"], trailing_avg.get(idx)),
                temperature_avg_c=temperature.temperature_avg_c if temperature else None,
            )
        )
    unusual_day_count = sum(point.is_unusual for point in daily_points)

    total_kwh = month_df["total_kwh"].sum()
    peak_total = month_df["peak_hours_kwh"].sum()
    off_peak_total = month_df["off_peak_hours_kwh"].sum()

    max_day = None
    if daily_points:
        max_day = max(daily_points, key=lambda p: p.total_kwh)

    prev_mask = (df.index.year == year - 1) & (df.index.month == month) if not df.empty else None
    previous_year_total = (
        float(df[prev_mask]["total_kwh"].sum())
        if prev_mask is not None and prev_mask.any()
        else None
    )
    delta_kwh = (total_kwh - previous_year_total) if previous_year_total is not None else None
    delta_pct = (delta_kwh / previous_year_total * 100) if previous_year_total else None

    # Rolling 30-day average as it stood right before the month started (KPI: "vs 30-day avg").
    month_start = pd.Timestamp(year=year, month=month, day=1)
    pre_month_avg = trailing_avg.get(month_start)
    daily_avg = total_kwh / len(daily_points) if daily_points else 0.0
    rolling_delta_pct = (
        (daily_avg - pre_month_avg) / pre_month_avg * 100
        if pre_month_avg is not None and not pd.isna(pre_month_avg) and pre_month_avg
        else None
    )

    return MonthSummary(
        year=year,
        month=month,
        total_kwh=total_kwh,
        peak_hours_kwh=peak_total,
        off_peak_hours_kwh=off_peak_total,
        peak_pct=(peak_total / total_kwh * 100) if total_kwh else 0.0,
        off_peak_pct=(off_peak_total / total_kwh * 100) if total_kwh else 0.0,
        daily_avg_kwh=daily_avg,
        max_day=max_day,
        co2_kg=total_kwh * settings.co2_factor_g_per_kwh / 1000,
        previous_year_total_kwh=previous_year_total,
        delta_kwh=delta_kwh,
        delta_pct=delta_pct,
        median_kwh=float(month_df["total_kwh"].median()) if daily_points else 0.0,
        stdev_kwh=float(month_df["total_kwh"].std(ddof=0)) if len(daily_points) > 1 else 0.0,
        min_kwh=float(month_df["total_kwh"].min()) if daily_points else 0.0,
        max_kwh=float(month_df["total_kwh"].max()) if daily_points else 0.0,
        rolling_30d_avg_kwh=(
            None if pre_month_avg is None or pd.isna(pre_month_avg) else float(pre_month_avg)
        ),
        rolling_30d_delta_pct=rolling_delta_pct,
        unusual_day_count=unusual_day_count,
        daily_points=daily_points,
    )


def get_annual_summary(session: Session, user_id: int, year: int) -> AnnualSummary:
    df = load_dataframe(session, user_id)
    months_current = monthly_totals(df, year)
    months_previous = monthly_totals(df, year - 1)
    temperatures = load_temperatures(session, user_id, date(year - 1, 1, 1), date(year, 12, 31))
    _apply_monthly_temperatures(months_current, temperatures, year)
    _apply_monthly_temperatures(months_previous, temperatures, year - 1)

    months_with_data = [m for m in months_current if m.total_kwh > 0]
    total_to_date = sum(m.total_kwh for m in months_with_data)
    monthly_avg = total_to_date / len(months_with_data) if months_with_data else 0.0
    max_month = max(months_with_data, key=lambda m: m.total_kwh, default=None)
    min_month = min(months_with_data, key=lambda m: m.total_kwh, default=None)

    season_totals = {
        season: sum(m.total_kwh for m in months_current if m.month in months)
        for season, months in SEASON_MONTHS.items()
    }

    year_df = df[df.index.year == year] if not df.empty else df
    calendar = {idx.date(): float(row["total_kwh"]) for idx, row in year_df.iterrows()}

    return AnnualSummary(
        year=year,
        months_current=months_current,
        months_previous=months_previous,
        total_to_date_kwh=total_to_date,
        monthly_avg_kwh=monthly_avg,
        max_month=max_month,
        min_month=min_month,
        season_totals=season_totals,
        calendar=calendar,
    )
