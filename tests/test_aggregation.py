"""Aggregation & forecast service tests (see docs/06-dashboard-views.md).

Dataset: flat 10 kWh/day (peak=6, off_peak=4) for all of 2025 and for
2026-01-01..2026-03-15, with a single outlier on 2026-03-10 (50 kWh total)
to exercise unusual-day detection.
"""

from datetime import date, timedelta

import pytest
from sqlmodel import Session

from app.db.models import ConsumptionRecord
from app.services.aggregation import get_annual_summary, get_month_summary
from app.services.forecast import compute_forecast

TODAY = date(2026, 3, 15)


def _insert_day(
    session: Session, user_id: int, day: date, peak: float, off_peak: float, batch_id: int
) -> None:
    session.add(
        ConsumptionRecord(
            user_id=user_id,
            import_batch_id=batch_id,
            date=day,
            peak_hours_kwh=peak,
            off_peak_hours_kwh=off_peak,
            total_kwh=peak + off_peak,
        )
    )


@pytest.fixture
def flat_dataset(session: Session, test_user):
    from app.db.models import ImportBatch

    batch = ImportBatch(user_id=test_user.id, source_filename="fixture.csv")
    session.add(batch)
    session.flush()

    day = date(2025, 1, 1)
    while day <= TODAY:
        peak, off_peak = (30.0, 20.0) if day == date(2026, 3, 10) else (6.0, 4.0)
        _insert_day(session, test_user.id, day, peak, off_peak, batch.id)
        day += timedelta(days=1)

    session.commit()
    return test_user


def test_month_summary_current_vs_previous_year(session: Session, flat_dataset) -> None:
    user = flat_dataset
    summary = get_month_summary(session, user.id, year=2026, month=3)

    assert summary.total_kwh == pytest.approx(14 * 10 + 50)
    assert summary.peak_hours_kwh == pytest.approx(14 * 6 + 30)
    assert summary.off_peak_hours_kwh == pytest.approx(14 * 4 + 20)
    assert summary.max_day is not None
    assert summary.max_day.date == date(2026, 3, 10)
    assert summary.max_day.total_kwh == pytest.approx(50)
    assert summary.unusual_day_count == 1

    assert summary.previous_year_total_kwh == pytest.approx(31 * 10)  # March 2025, full month
    assert summary.delta_kwh == pytest.approx(summary.total_kwh - 310)
    assert summary.delta_pct == pytest.approx((summary.total_kwh - 310) / 310 * 100)

    assert summary.median_kwh == pytest.approx(10.0)
    assert summary.rolling_30d_avg_kwh == pytest.approx(10.0, abs=0.5)


def test_month_summary_with_no_data_is_empty_not_an_error(session: Session, flat_dataset) -> None:
    user = flat_dataset
    summary = get_month_summary(session, user.id, year=2030, month=1)

    assert summary.total_kwh == 0.0
    assert summary.max_day is None
    assert summary.unusual_day_count == 0
    assert summary.previous_year_total_kwh is None


def test_annual_summary_totals_and_seasons(session: Session, flat_dataset) -> None:
    user = flat_dataset
    summary = get_annual_summary(session, user.id, year=2026)

    assert summary.total_to_date_kwh == pytest.approx(31 * 10 + 28 * 10 + (14 * 10 + 50))
    assert summary.max_month is not None
    assert summary.max_month.month == 1  # January, 31 days, is the biggest realized month
    assert summary.min_month is not None
    assert summary.min_month.month == 3  # partial month, smallest total

    # winter = Dec(0, no data yet) + Jan + Feb
    assert summary.season_totals["winter"] == pytest.approx(31 * 10 + 28 * 10)
    assert summary.season_totals["summer"] == pytest.approx(0.0)

    assert len(summary.calendar) == 31 + 28 + 15  # Jan+Feb+ (Mar 1-15)
    assert summary.calendar[date(2026, 3, 10)] == pytest.approx(50.0)

    previous = get_annual_summary(session, user.id, year=2025)
    assert len(previous.months_current) == 12
    assert previous.months_current[0].total_kwh == pytest.approx(31 * 10)  # January 2025


def test_forecast_applies_current_rate_to_previous_year_shape(
    session: Session, flat_dataset
) -> None:
    user = flat_dataset
    result = compute_forecast(session, user.id, year=2026, today=TODAY)

    to_date_current = 31 * 10 + 28 * 10 + (14 * 10 + 50)
    to_date_previous = 31 * 10 + 28 * 10 + 15 * 10
    expected_ratio = to_date_current / to_date_previous
    assert result.rate_ratio == pytest.approx(expected_ratio)

    # Jan/Feb are fully completed; March is in progress (today=2026-03-15) so it gets a
    # remainder-only forecast too — only then April..December are forecast in full.
    assert result.in_progress_month == 3
    assert set(result.monthly_forecast) == set(range(3, 13))

    # March 2025 had 31 days at 10 kWh/day; 15 days (through the 15th) are "already elapsed".
    march_remainder = (31 - 15) * 10
    assert result.monthly_forecast[3] == pytest.approx(march_remainder * expected_ratio)

    previous_year_days_by_month = {4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
    for month, days in previous_year_days_by_month.items():
        assert result.monthly_forecast[month] == pytest.approx(days * 10 * expected_ratio)

    expected_remaining = result.monthly_forecast[3] + sum(
        days * 10 * expected_ratio for days in previous_year_days_by_month.values()
    )
    assert result.estimated_annual_total_kwh == pytest.approx(to_date_current + expected_remaining)

    # December only falls in "winter"; March/April/May in "spring"; June-Aug in "summer";
    # Sep-Nov in "autumn".
    assert result.season_forecast["winter"] == pytest.approx(result.monthly_forecast[12])
    assert result.season_forecast["spring"] == pytest.approx(
        result.monthly_forecast[3] + result.monthly_forecast[4] + result.monthly_forecast[5]
    )


def test_forecast_in_progress_month_does_not_double_count_actuals(
    session: Session, flat_dataset
) -> None:
    """Regression test: forecasting an unfinished month must not bias the total downward
    (by ignoring its remainder) nor double-count the days already recorded."""
    user = flat_dataset
    result = compute_forecast(session, user.id, year=2026, today=TODAY)

    # The remainder-only forecast for March must be strictly less than a full month's
    # worth (it only covers the ~16 days not yet elapsed), but still greater than zero.
    full_march_estimate = 31 * 10 * result.rate_ratio
    assert 0 < result.monthly_forecast[3] < full_march_estimate

    # estimated_annual_total already includes March's actual-to-date (via to_date_current),
    # so adding the remainder must not double count it.
    to_date_current = 31 * 10 + 28 * 10 + (14 * 10 + 50)
    assert result.estimated_annual_total_kwh > to_date_current + result.monthly_forecast[3]


def test_forecast_with_no_previous_year_data_falls_back_to_ratio_one(
    session: Session, test_user
) -> None:
    result = compute_forecast(session, test_user.id, year=2026, today=TODAY)
    assert result.rate_ratio == 1.0
    assert result.monthly_forecast == {}
    assert result.estimated_annual_total_kwh == 0.0
