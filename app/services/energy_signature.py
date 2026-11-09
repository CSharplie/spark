"""Energy signature: daily kWh vs outdoor temperature, split into base load, heating and cooling.

Fits `kWh = base + a·HDD(Th) + c·CDD(Tc)` by least squares, where HDD/CDD are the
heating/cooling degree-days of each day's average temperature. The balance temperatures
Th/Tc are searched on a grid, and heating/cooling are only kept when their slope is
significantly positive, so the model adapts to each household and period.
See docs/06-dashboard-views.md.
"""

from dataclasses import dataclass, replace
from datetime import date, timedelta

import numpy as np
from sqlmodel import Session, and_, func, select

from app.db.models import ConsumptionRecord, DailyTemperature

MIN_DAYS = 60
WINDOW_DAYS = 365
HEATING_BALANCE_RANGE = np.arange(10.0, 22.01, 0.5)
COOLING_BALANCE_RANGE = np.arange(16.0, 28.01, 0.5)
OUTLIER_SIGMA = 3.0
ABSENCE_RATIO = 0.5  # a day under half the base load is treated as an absence
MIN_T_STAT = 1.65  # one-sided 95 % significance for a heating/cooling slope
MIN_ACTIVE_DAYS = 10  # days beyond a balance temperature needed to estimate its slope
# Neither heating nor cooling runs in between; without it a V can fit heating curvature.
MIN_NEUTRAL_BAND_C = 3.0


@dataclass(frozen=True)
class DayPoint:
    date: date
    total_kwh: float
    temperature_avg_c: float


@dataclass(frozen=True)
class Signature:
    base_kwh: float  # per day
    heating_kwh_per_dd: float | None  # None: no heating detected
    heating_balance_c: float | None
    cooling_kwh_per_dd: float | None  # None: no cooling detected
    cooling_balance_c: float | None
    r2: float
    n_days: int

    def heating_degree_days(self, temps: np.ndarray) -> np.ndarray:
        if self.heating_balance_c is None:
            return np.zeros_like(temps)
        return np.maximum(0.0, self.heating_balance_c - temps)

    def cooling_degree_days(self, temps: np.ndarray) -> np.ndarray:
        if self.cooling_balance_c is None:
            return np.zeros_like(temps)
        return np.maximum(0.0, temps - self.cooling_balance_c)

    def predict(self, temps: np.ndarray) -> np.ndarray:
        return (
            self.base_kwh
            + (self.heating_kwh_per_dd or 0.0) * self.heating_degree_days(temps)
            + (self.cooling_kwh_per_dd or 0.0) * self.cooling_degree_days(temps)
        )


@dataclass(frozen=True)
class PeriodAnalysis:
    signature: Signature | None
    window: list[DayPoint]  # days the signature was fitted on
    period: list[DayPoint]  # days of the selected period that have a temperature
    base_kwh: float  # model estimates over `period`
    heating_kwh: float
    cooling_kwh: float
    weather_adjusted_change_pct: float | None  # vs the same period one year earlier

    @property
    def heating_share_pct(self) -> float | None:
        modelled = self.base_kwh + self.heating_kwh + self.cooling_kwh
        return self.heating_kwh / modelled * 100 if modelled > 0 else None

    @property
    def cooling_share_pct(self) -> float | None:
        modelled = self.base_kwh + self.heating_kwh + self.cooling_kwh
        return self.cooling_kwh / modelled * 100 if modelled > 0 else None


def _design(temps: np.ndarray, th: float | None, tc: float | None) -> np.ndarray:
    columns = [np.ones_like(temps)]
    if th is not None:
        columns.append(np.maximum(0.0, th - temps))
    if tc is not None:
        columns.append(np.maximum(0.0, temps - tc))
    return np.column_stack(columns)


def _candidates() -> list[tuple[float | None, float | None]]:
    heating = [float(th) for th in HEATING_BALANCE_RANGE]
    cooling = [float(tc) for tc in COOLING_BALANCE_RANGE]
    return [
        (None, None),
        *((th, None) for th in heating),
        *((None, tc) for tc in cooling),
        *((th, tc) for th in heating for tc in cooling if tc - th >= MIN_NEUTRAL_BAND_C),
    ]


def _best_model(temps: np.ndarray, kwh: np.ndarray) -> Signature:
    """Best fit (lowest SSE) per structure, then the most complete structure whose slopes
    are all significant: heating+cooling, else heating or cooling alone, else constant."""
    n = len(temps)
    best_per_structure: dict[tuple[bool, bool], tuple[float, float | None, float | None]] = {}
    for th, tc in _candidates():
        design = _design(temps, th, tc)
        if np.any(np.count_nonzero(design[:, 1:], axis=0) < MIN_ACTIVE_DAYS):
            continue
        coef, *_ = np.linalg.lstsq(design, kwh, rcond=None)
        if np.any(coef[1:] <= 0):
            continue
        sse = float(np.sum((kwh - design @ coef) ** 2))
        structure = (th is not None, tc is not None)
        if structure not in best_per_structure or sse < best_per_structure[structure][0]:
            best_per_structure[structure] = (sse, th, tc)

    significant: list[tuple[int, float, Signature]] = []
    for sse, th, tc in best_per_structure.values():
        design = _design(temps, th, tc)
        coef, *_ = np.linalg.lstsq(design, kwh, rcond=None)
        if len(coef) > 1:
            variance = sse / max(n - len(coef), 1)
            std_err = np.sqrt(np.diag(variance * np.linalg.pinv(design.T @ design)))[1:]
            if np.any(coef[1:] < MIN_T_STAT * std_err):
                continue
        slopes = iter(coef[1:])
        signature = Signature(
            base_kwh=float(coef[0]),
            heating_kwh_per_dd=float(next(slopes)) if th is not None else None,
            heating_balance_c=th,
            cooling_kwh_per_dd=float(next(slopes)) if tc is not None else None,
            cooling_balance_c=tc,
            r2=0.0,
            n_days=n,
        )
        significant.append((-(len(coef) - 1), sse, signature))
    # The constant model has no slope to test, so it is always in the list.
    return min(significant, key=lambda item: item[:2])[2]


def _with_r2(signature: Signature, temps: np.ndarray, kwh: np.ndarray) -> Signature:
    sst = float(np.sum((kwh - kwh.mean()) ** 2))
    sse = float(np.sum((kwh - signature.predict(temps)) ** 2))
    r2 = 1 - sse / sst if sst > 0 else 0.0
    return replace(signature, r2=r2, n_days=len(temps))


def fit_signature(days: list[DayPoint]) -> Signature | None:
    """Best-fitting signature for `days`, or None with fewer than MIN_DAYS days."""
    if len(days) < MIN_DAYS:
        return None
    temps = np.array([d.temperature_avg_c for d in days])
    kwh = np.array([d.total_kwh for d in days])

    first = _best_model(temps, kwh)
    # Absences (holidays: near-empty home, often in hot weather) would hide cooling, and
    # outliers (guests...) skew the slopes: drop both, then refit.
    kept = kwh >= ABSENCE_RATIO * first.base_kwh
    if kept.sum() < MIN_DAYS:
        return _with_r2(first, temps, kwh)
    signature = _best_model(temps[kept], kwh[kept])
    residuals = kwh - signature.predict(temps)
    not_outlier = np.abs(residuals) <= OUTLIER_SIGMA * residuals[kept].std()
    if (kept & not_outlier).sum() >= MIN_DAYS and not np.array_equal(kept & not_outlier, kept):
        kept &= not_outlier
        signature = _best_model(temps[kept], kwh[kept])
    return _with_r2(signature, temps[kept], kwh[kept])


def load_days(session: Session, user_id: int, start: date, end: date) -> list[DayPoint]:
    """`user_id`'s consumption days between `start` and `end` that have a temperature."""
    rows = session.exec(
        select(
            ConsumptionRecord.date,
            ConsumptionRecord.total_kwh,
            DailyTemperature.temperature_avg_c,
        )
        .join(
            DailyTemperature,
            and_(
                DailyTemperature.user_id == ConsumptionRecord.user_id,
                DailyTemperature.date == ConsumptionRecord.date,
            ),
        )
        .where(
            ConsumptionRecord.user_id == user_id,
            ConsumptionRecord.date >= start,
            ConsumptionRecord.date <= end,
        )
        .order_by(ConsumptionRecord.date)
    )
    return [DayPoint(date=d, total_kwh=kwh, temperature_avg_c=temp) for d, kwh, temp in rows]


def _one_year_earlier(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29 February
        return day.replace(year=day.year - 1, day=28)


def _fit_window(
    session: Session, user_id: int, start: date, end: date
) -> tuple[Signature | None, list[DayPoint]]:
    """Fit on at least WINDOW_DAYS days ending at `end`, so heating and cooling seasons are
    both represented even when the selected period is a single month."""
    window_start = min(start, end - timedelta(days=WINDOW_DAYS - 1))
    window = load_days(session, user_id, window_start, end)
    return fit_signature(window), window


def analyze_period(session: Session, user_id: int, start: date, end: date) -> PeriodAnalysis:
    latest = session.exec(
        select(func.max(ConsumptionRecord.date)).where(ConsumptionRecord.user_id == user_id)
    ).one()
    effective_end = min(end, latest) if latest else end

    signature, window = _fit_window(session, user_id, start, effective_end)
    period = [d for d in window if start <= d.date <= end]

    base = heating = cooling = 0.0
    if signature and period:
        temps = np.array([d.temperature_avg_c for d in period])
        base = signature.base_kwh * len(period)
        heating = float(
            (signature.heating_kwh_per_dd or 0.0) * signature.heating_degree_days(temps).sum()
        )
        cooling = float(
            (signature.cooling_kwh_per_dd or 0.0) * signature.cooling_degree_days(temps).sum()
        )

    change_pct = None
    if period:
        reference, _ = _fit_window(
            session, user_id, _one_year_earlier(start), _one_year_earlier(effective_end)
        )
        if reference:
            # What last year's household would have used under this period's weather.
            expected = float(
                reference.predict(np.array([d.temperature_avg_c for d in period])).sum()
            )
            actual = sum(d.total_kwh for d in period)
            if expected > 0:
                change_pct = (actual - expected) / expected * 100

    return PeriodAnalysis(
        signature=signature,
        window=window,
        period=period,
        base_kwh=base,
        heating_kwh=heating,
        cooling_kwh=cooling,
        weather_adjusted_change_pct=change_pct,
    )
