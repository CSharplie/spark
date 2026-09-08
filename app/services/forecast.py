"""Year-end forecast: apply year N's realized daily rate to year N-1's monthly shape.

See docs/06-dashboard-views.md. Simplification: computed at monthly granularity
(not daily) — enough to drive the dashed cumulative line and the season
real/forecast split without over-engineering a full daily projection.
"""

from dataclasses import dataclass, field
from datetime import date

from sqlmodel import Session

from app.services.aggregation import SEASON_MONTHS, load_dataframe, monthly_totals


@dataclass
class ForecastResult:
    year: int
    rate_ratio: float
    # Only the not-yet-observed kWh per month: the full month for months that haven't
    # started yet, or just the remaining days for `in_progress_month` (never double-counts
    # kWh already recorded — see the in-progress-month handling in compute_forecast).
    monthly_forecast: dict[int, float] = field(default_factory=dict)
    estimated_annual_total_kwh: float = 0.0
    season_forecast: dict[str, float] = field(default_factory=dict)
    # The current calendar month, if `year` is the current year and that month isn't over yet.
    in_progress_month: int | None = None


def compute_forecast(
    session: Session, user_id: int, year: int, today: date | None = None
) -> ForecastResult:
    today = today or date.today()
    df = load_dataframe(session, user_id)

    if df.empty:
        return ForecastResult(year=year, rate_ratio=1.0)

    in_progress_month = today.month if year == today.year else None
    if year == today.year:
        completed_months = set(range(1, today.month))  # strictly before the in-progress month
    elif year < today.year:
        completed_months = set(range(1, 13))
    else:
        completed_months = set()

    cutoff_current = (
        date(year, today.month, min(today.day, 28)) if year == today.year else date(year, 12, 31)
    )
    cutoff_previous = cutoff_current.replace(year=year - 1)

    to_date_current = df[(df.index.year == year) & (df.index.date <= cutoff_current)][
        "total_kwh"
    ].sum()
    to_date_previous = df[(df.index.year == year - 1) & (df.index.date <= cutoff_previous)][
        "total_kwh"
    ].sum()
    rate_ratio = float(to_date_current / to_date_previous) if to_date_previous else 1.0

    months_previous = monthly_totals(df, year - 1)
    months_previous_by_month = {m.month: m for m in months_previous}

    # Months that haven't started yet at all: forecast the whole month from last year's shape.
    monthly_forecast: dict[int, float] = {
        m.month: m.total_kwh * rate_ratio
        for m in months_previous
        if m.month not in completed_months and m.month != in_progress_month
    }

    # The in-progress month already has partial actual data — only forecast its *remainder*
    # (the previous year's total for the days not yet elapsed this month), so we never add a
    # forecast on top of kWh that's already been recorded (that was the source of the bias).
    if in_progress_month is not None:
        prev_month = months_previous_by_month.get(in_progress_month)
        prev_month_total = prev_month.total_kwh if prev_month is not None else 0.0
        prev_month_to_date = df[
            (df.index.year == year - 1)
            & (df.index.month == in_progress_month)
            & (df.index.date <= cutoff_previous)
        ]["total_kwh"].sum()
        remainder = max(prev_month_total - prev_month_to_date, 0.0)
        monthly_forecast[in_progress_month] = remainder * rate_ratio

    # `to_date_current` already covers every kWh actually recorded this year (completed
    # months + the in-progress month's partial data), so adding the (remainder-only)
    # monthly_forecast on top never double-counts.
    estimated_annual_total = float(to_date_current + sum(monthly_forecast.values()))

    season_forecast = {season: 0.0 for season in SEASON_MONTHS}
    for month, value in monthly_forecast.items():
        for season, months in SEASON_MONTHS.items():
            if month in months:
                season_forecast[season] += value

    return ForecastResult(
        year=year,
        rate_ratio=rate_ratio,
        monthly_forecast=monthly_forecast,
        estimated_annual_total_kwh=estimated_annual_total,
        season_forecast=season_forecast,
        in_progress_month=in_progress_month,
    )
