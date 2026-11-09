"""Builds ECharts `option` dicts from aggregation dataclasses, localized via t().

See docs/06-dashboard-views.md. Kept separate from aggregation.py: aggregation
produces plain data, this module formats it for a specific chart/locale.
"""

import math
from collections.abc import Callable
from datetime import date as date_
from typing import Any

import numpy as np
from babel.dates import format_date

from app.services.aggregation import AnnualSummary, MonthSummary
from app.services.energy_signature import DayPoint, PeriodAnalysis
from app.services.forecast import ForecastResult

PEAK_COLOR = "#ea580c"  # orange-600
OFF_PEAK_COLOR = "#f59e0b"  # amber-500
UNUSUAL_COLOR = "#dc2626"  # red-600
PREVIOUS_YEAR_COLOR = "#94a3b8"  # slate-400
CURRENT_YEAR_COLOR = "#2563eb"  # blue-600
TEMPERATURE_AVG_COLOR = "#0f766e"  # teal-700
PREVIOUS_YEAR_TEMPERATURE_COLOR = "#5eead4"  # teal-300

SEASON_ORDER = ("winter", "spring", "summer", "autumn")


def _month_labels(locale: str) -> list[str]:
    return [format_date(date_(2000, m, 1), format="MMM", locale=locale) for m in range(1, 13)]


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _kwh_axis(**extra: Any) -> dict[str, Any]:
    # Unit in the tick labels rather than an axis name, which collides with the legend.
    return {"type": "value", "axisLabel": {"formatter": "{value} kWh"}, **extra}


def _temperature_axis(**extra: Any) -> dict[str, Any]:
    # `scale` lets the axis follow the data (incl. negatives) instead of starting at 0.
    return {
        "type": "value",
        "scale": True,
        "splitLine": {"show": False},
        "axisLabel": {"formatter": "{value} °C"},
        **extra,
    }


def _temperature_line(
    name: str, data: list[float | None], color: str, **line_style: Any
) -> dict[str, Any]:
    return {
        "name": name,
        "type": "line",
        "data": data,
        "smooth": True,
        "showSymbol": False,
        "z": 3,
        "itemStyle": {"color": color},
        "lineStyle": {"color": color, "width": 2, **line_style},
    }


def daily_chart_option(summary: MonthSummary, t: Callable[..., str]) -> dict[str, Any]:
    points = summary.daily_points
    dates = [p.date.isoformat() for p in points]
    peak = [round(p.peak_hours_kwh, 3) for p in points]
    off_peak = [round(p.off_peak_hours_kwh, 3) for p in points]
    unusual = [
        {"value": [p.date.isoformat(), round(p.total_kwh, 3)]} for p in points if p.is_unusual
    ]

    temperature_series: list[dict[str, Any]] = []
    if any(p.temperature_avg_c is not None for p in points):
        temperature_series = [
            {
                **_temperature_line(
                    t("chart.temperature_avg"),
                    [_round(p.temperature_avg_c) for p in points],
                    TEMPERATURE_AVG_COLOR,
                ),
                "yAxisIndex": 1,
            }
        ]
    y_axes: list[dict[str, Any]] = [_kwh_axis()]
    if temperature_series:
        y_axes.append(_temperature_axis())

    return {
        "tooltip": {"trigger": "axis"},
        "legend": {
            "type": "scroll",
            "bottom": 0,
            "data": [
                t("consumption.peak_hours"),
                t("consumption.off_peak_hours"),
                *(s["name"] for s in temperature_series),
            ],
        },
        "grid": {"containLabel": True, "left": 8, "right": 16, "top": 16, "bottom": 40},
        "xAxis": {"type": "category", "data": dates},
        "yAxis": y_axes,
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
            *temperature_series,
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

    temperature_series: list[dict[str, Any]] = []
    if any(
        m.temperature_avg_c is not None for m in summary.months_current + summary.months_previous
    ):
        temperature_series = [
            _temperature_line(
                t("chart.temperature_avg_previous_year"),
                [_round(m.temperature_avg_c) for m in summary.months_previous],
                PREVIOUS_YEAR_TEMPERATURE_COLOR,
                type="dashed",
            ),
            _temperature_line(
                t("chart.temperature_avg_current_year"),
                [_round(m.temperature_avg_c) for m in summary.months_current],
                TEMPERATURE_AVG_COLOR,
            ),
        ]
        for series in temperature_series:
            series["xAxisIndex"] = 0
            series["yAxisIndex"] = 2
    y_axes: list[dict[str, Any]] = [_kwh_axis(gridIndex=0), _kwh_axis(gridIndex=1)]
    if temperature_series:
        y_axes.append(_temperature_axis(gridIndex=0))

    return {
        "tooltip": {"trigger": "axis"},
        "legend": [
            {
                "type": "scroll",
                "data": [
                    t("consumption.previous_year"),
                    t("consumption.current_year"),
                    t("chart.forecast"),
                    *(s["name"] for s in temperature_series),
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
        "yAxis": y_axes,
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
            *temperature_series,
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


def energy_signature_option(analysis: PeriodAnalysis, t: Callable[..., str]) -> dict[str, Any]:
    """kWh/day vs average temperature: model window days, selected period days, fitted curve."""
    signature = analysis.signature
    if signature is None:
        return {
            "title": {
                "text": t("dashboard.weather.not_enough_data"),
                "left": "center",
                "top": "middle",
                "textStyle": {"fontSize": 13, "fontWeight": "normal", "color": "#94a3b8"},
            }
        }

    period_days = {d.date for d in analysis.period}

    def point(d: DayPoint) -> list[Any]:
        return [round(d.temperature_avg_c, 1), round(d.total_kwh, 1), d.date.isoformat()]

    temps = [d.temperature_avg_c for d in analysis.window]
    curve_x = np.arange(math.floor(min(temps)), math.ceil(max(temps)) + 0.5, 0.5)
    curve = [
        [float(x), round(float(y), 1)]
        for x, y in zip(curve_x, signature.predict(curve_x), strict=True)
    ]

    return {
        "tooltip": {"trigger": "item"},
        "legend": {
            "type": "scroll",
            "bottom": 0,
            "data": [t("chart.signature_window"), t("chart.signature_period"), t("chart.model")],
        },
        "grid": {"containLabel": True, "left": 8, "right": 16, "top": 16, "bottom": 40},
        "xAxis": {"type": "value", "scale": True, "axisLabel": {"formatter": "{value} °C"}},
        "yAxis": _kwh_axis(),
        "series": [
            {
                "name": t("chart.signature_window"),
                "type": "scatter",
                "data": [point(d) for d in analysis.window if d.date not in period_days],
                "symbolSize": 5,
                "itemStyle": {"color": PREVIOUS_YEAR_COLOR, "opacity": 0.5},
            },
            {
                "name": t("chart.signature_period"),
                "type": "scatter",
                "data": [point(d) for d in analysis.period],
                "symbolSize": 7,
                "itemStyle": {"color": CURRENT_YEAR_COLOR},
            },
            {
                "name": t("chart.model"),
                "type": "line",
                "data": curve,
                "showSymbol": False,
                "z": 3,
                "itemStyle": {"color": TEMPERATURE_AVG_COLOR},
                "lineStyle": {"color": TEMPERATURE_AVG_COLOR, "width": 2},
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
