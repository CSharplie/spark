"""Builds ECharts `option` dicts from aggregation dataclasses, localized via t().

See docs/06-dashboard-views.md. Kept separate from aggregation.py: aggregation
produces plain data, this module formats it for a specific chart/locale.
"""

from collections.abc import Callable
from datetime import date as date_
from typing import Any

from babel.dates import format_date

from app.services.aggregation import AnnualSummary, MonthSummary
from app.services.forecast import ForecastResult

PEAK_COLOR = "#ea580c"  # orange-600
OFF_PEAK_COLOR = "#f59e0b"  # amber-500
UNUSUAL_COLOR = "#dc2626"  # red-600
PREVIOUS_YEAR_COLOR = "#94a3b8"  # slate-400
CURRENT_YEAR_COLOR = "#2563eb"  # blue-600

SEASON_ORDER = ("winter", "spring", "summer", "autumn")


def _month_labels(locale: str) -> list[str]:
    return [format_date(date_(2000, m, 1), format="MMM", locale=locale) for m in range(1, 13)]


def daily_chart_option(summary: MonthSummary, t: Callable[..., str]) -> dict[str, Any]:
    dates = [p.date.isoformat() for p in summary.daily_points]
    peak = [round(p.peak_hours_kwh, 3) for p in summary.daily_points]
    off_peak = [round(p.off_peak_hours_kwh, 3) for p in summary.daily_points]
    unusual = [
        {"value": [p.date.isoformat(), round(p.total_kwh, 3)]}
        for p in summary.daily_points
        if p.is_unusual
    ]

    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": [t("consumption.peak_hours"), t("consumption.off_peak_hours")]},
        "grid": {"containLabel": True, "left": 8, "right": 16, "top": 32, "bottom": 24},
        "xAxis": {"type": "category", "data": dates},
        "yAxis": {"type": "value", "name": "kWh"},
        "series": [
            {
                "name": t("consumption.peak_hours"),
                "type": "bar",
                "stack": "total",
                "data": peak,
                "itemStyle": {"color": PEAK_COLOR},
            },
            {
                "name": t("consumption.off_peak_hours"),
                "type": "bar",
                "stack": "total",
                "data": off_peak,
                "itemStyle": {"color": OFF_PEAK_COLOR},
            },
            {
                "name": t("consumption.unusual_day"),
                "type": "scatter",
                "data": unusual,
                "symbolSize": 10,
                "itemStyle": {"color": UNUSUAL_COLOR},
            },
        ],
    }


def split_pie_option(summary: MonthSummary, t: Callable[..., str]) -> dict[str, Any]:
    return {
        "tooltip": {"trigger": "item"},
        "legend": {"bottom": 0},
        "series": [
            {
                "type": "pie",
                "radius": ["40%", "70%"],
                "data": [
                    {
                        "name": t("consumption.peak_hours"),
                        "value": round(summary.peak_hours_kwh, 3),
                        "itemStyle": {"color": PEAK_COLOR},
                    },
                    {
                        "name": t("consumption.off_peak_hours"),
                        "value": round(summary.off_peak_hours_kwh, 3),
                        "itemStyle": {"color": OFF_PEAK_COLOR},
                    },
                ],
            }
        ],
    }


def month_comparison_option(summary: MonthSummary, t: Callable[..., str]) -> dict[str, Any]:
    previous = summary.previous_year_total_kwh or 0.0
    return {
        "tooltip": {"trigger": "axis"},
        "grid": {"containLabel": True, "left": 8, "right": 16, "top": 16, "bottom": 24},
        "xAxis": {
            "type": "category",
            "data": [t("consumption.previous_year"), t("consumption.current_year")],
        },
        "yAxis": {"type": "value", "name": "kWh"},
        "series": [
            {
                "type": "bar",
                "data": [
                    {"value": round(previous, 3), "itemStyle": {"color": PREVIOUS_YEAR_COLOR}},
                    {
                        "value": round(summary.total_kwh, 3),
                        "itemStyle": {"color": CURRENT_YEAR_COLOR},
                    },
                ],
            }
        ],
    }


def monthly_summary_option(
    summary: AnnualSummary, forecast: ForecastResult, t: Callable[..., str], locale: str
) -> dict[str, Any]:
    """Two stacked subplots in one chart: N vs N-1 totals (top, with forecast on top of N
    for the in-progress/future months), peak/off-peak split (bottom)."""
    labels = _month_labels(locale)
    current_totals = [round(m.total_kwh, 1) for m in summary.months_current]
    previous_totals = [round(m.total_kwh, 1) for m in summary.months_previous]
    forecast_totals = [
        round(forecast.monthly_forecast.get(month, 0.0), 1) for month in range(1, 13)
    ]
    peak = [round(m.peak_hours_kwh, 1) for m in summary.months_current]
    off_peak = [round(m.off_peak_hours_kwh, 1) for m in summary.months_current]

    return {
        "tooltip": {"trigger": "axis"},
        "legend": [
            {
                "data": [
                    t("consumption.previous_year"),
                    t("consumption.current_year"),
                    t("chart.forecast"),
                ],
                "top": 0,
            },
            {
                "data": [t("consumption.peak_hours"), t("consumption.off_peak_hours")],
                "top": "54%",
            },
        ],
        "grid": [
            {"left": 8, "right": 16, "top": 32, "height": "38%", "containLabel": True},
            {"left": 8, "right": 16, "top": "62%", "bottom": 24, "containLabel": True},
        ],
        "xAxis": [
            {"type": "category", "data": labels, "gridIndex": 0},
            {"type": "category", "data": labels, "gridIndex": 1},
        ],
        "yAxis": [
            {"type": "value", "name": "kWh", "gridIndex": 0},
            {"type": "value", "name": "kWh", "gridIndex": 1},
        ],
        "series": [
            {
                "name": t("consumption.previous_year"),
                "type": "bar",
                "data": previous_totals,
                "xAxisIndex": 0,
                "yAxisIndex": 0,
                "itemStyle": {"color": PREVIOUS_YEAR_COLOR},
            },
            {
                "name": t("consumption.current_year"),
                "type": "bar",
                "stack": "current",
                "data": current_totals,
                "xAxisIndex": 0,
                "yAxisIndex": 0,
                "itemStyle": {"color": CURRENT_YEAR_COLOR},
            },
            {
                "name": t("chart.forecast"),
                "type": "bar",
                "stack": "current",
                "data": forecast_totals,
                "xAxisIndex": 0,
                "yAxisIndex": 0,
                "itemStyle": {"color": CURRENT_YEAR_COLOR, "opacity": 0.4},
            },
            {
                "name": t("consumption.peak_hours"),
                "type": "bar",
                "stack": "split",
                "data": peak,
                "xAxisIndex": 1,
                "yAxisIndex": 1,
                "itemStyle": {"color": PEAK_COLOR},
            },
            {
                "name": t("consumption.off_peak_hours"),
                "type": "bar",
                "stack": "split",
                "data": off_peak,
                "xAxisIndex": 1,
                "yAxisIndex": 1,
                "itemStyle": {"color": OFF_PEAK_COLOR},
            },
        ],
    }


def cumulative_option(
    summary: AnnualSummary, forecast: ForecastResult, t: Callable[..., str], locale: str
) -> dict[str, Any]:
    labels = _month_labels(locale)
    realized_months = sorted(set(range(1, 13)) - set(forecast.monthly_forecast))

    cumulative_previous: list[float] = []
    running = 0.0
    for m in summary.months_previous:
        running += m.total_kwh
        cumulative_previous.append(round(running, 1))

    cumulative_current: list[float | None] = []
    running = 0.0
    for m in summary.months_current:
        if m.month in realized_months:
            running += m.total_kwh
            cumulative_current.append(round(running, 1))
        else:
            cumulative_current.append(None)

    last_realized_value = cumulative_current[max(realized_months) - 1] if realized_months else 0.0
    cumulative_forecast: list[float | None] = [None] * 12
    if realized_months:
        cumulative_forecast[max(realized_months) - 1] = last_realized_value
    running_forecast = last_realized_value or 0.0
    for month in range(1, 13):
        if month not in forecast.monthly_forecast:
            continue
        increment = forecast.monthly_forecast[month]
        if month == forecast.in_progress_month:
            # monthly_forecast[in_progress_month] is remainder-only (see compute_forecast);
            # add back what's already been recorded so this point reflects the full month.
            increment += summary.months_current[month - 1].total_kwh
        running_forecast += increment
        cumulative_forecast[month - 1] = round(running_forecast, 1)

    return {
        "tooltip": {"trigger": "axis"},
        "legend": {
            "data": [
                t("consumption.previous_year"),
                t("consumption.current_year"),
                t("chart.forecast"),
            ]
        },
        "grid": {"containLabel": True, "left": 8, "right": 16, "top": 40, "bottom": 24},
        "xAxis": {"type": "category", "data": labels},
        "yAxis": {"type": "value", "name": "kWh"},
        "series": [
            {
                "name": t("consumption.previous_year"),
                "type": "line",
                "data": cumulative_previous,
                "itemStyle": {"color": PREVIOUS_YEAR_COLOR},
            },
            {
                "name": t("consumption.current_year"),
                "type": "line",
                "data": cumulative_current,
                "itemStyle": {"color": CURRENT_YEAR_COLOR},
            },
            {
                "name": t("chart.forecast"),
                "type": "line",
                "data": cumulative_forecast,
                "lineStyle": {"type": "dashed"},
                "itemStyle": {"color": CURRENT_YEAR_COLOR},
                "connectNulls": True,
            },
        ],
    }


def season_split_option(
    summary: AnnualSummary, forecast: ForecastResult, t: Callable[..., str]
) -> dict[str, Any]:
    season_labels = {season: t(f"season.{season}") for season in SEASON_ORDER}
    real = [round(summary.season_totals.get(season, 0.0), 1) for season in SEASON_ORDER]
    forecasted = [round(forecast.season_forecast.get(season, 0.0), 1) for season in SEASON_ORDER]

    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": [t("chart.actual"), t("chart.forecast")]},
        "grid": {"containLabel": True, "left": 8, "right": 16, "top": 40, "bottom": 24},
        "xAxis": {"type": "category", "data": [season_labels[s] for s in SEASON_ORDER]},
        "yAxis": {"type": "value", "name": "kWh"},
        "series": [
            {
                "name": t("chart.actual"),
                "type": "bar",
                "stack": "season",
                "data": real,
                "itemStyle": {"color": CURRENT_YEAR_COLOR},
            },
            {
                "name": t("chart.forecast"),
                "type": "bar",
                "stack": "season",
                "data": forecasted,
                "itemStyle": {"color": CURRENT_YEAR_COLOR, "opacity": 0.4},
            },
        ],
    }


def calendar_heatmap_option(summary: AnnualSummary, year: int) -> dict[str, Any]:
    data = [[d.isoformat(), round(v, 2)] for d, v in sorted(summary.calendar.items())]
    max_value = max((v for _, v in data), default=1) or 1

    return {
        "tooltip": {"formatter": "{c} kWh"},
        "visualMap": {
            "min": 0,
            "max": max_value,
            "calculable": True,
            "orient": "horizontal",
            "left": "center",
            "top": 0,
        },
        "calendar": {
            "range": str(year),
            "cellSize": [16, 16],
            "top": 48,
            "yearLabel": {"show": False},
        },
        "series": [{"type": "heatmap", "coordinateSystem": "calendar", "data": data}],
    }
