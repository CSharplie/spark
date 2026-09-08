"""Monthly dashboard page + HTMX chart partials.

See docs/05-api-routes.md and docs/06-dashboard-views.md.
"""

from datetime import date

from babel.dates import format_date
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlmodel import Session, select

from app.core.deps import get_current_user
from app.core.security import generate_csrf_token, issue_csrf_cookie
from app.core.templates import get_request_translator, render
from app.db.models import ConsumptionRecord, User
from app.db.session import get_session
from app.services import chart_options
from app.services.aggregation import get_annual_summary, get_month_summary
from app.services.forecast import compute_forecast

router = APIRouter()


def _available_years(session: Session, user_id: int) -> list[int]:
    dates = session.exec(
        select(ConsumptionRecord.date).where(ConsumptionRecord.user_id == user_id)
    ).all()
    return sorted({d.year for d in dates}, reverse=True)


def _default_year_month(session: Session, user_id: int) -> tuple[int, int]:
    latest = session.exec(
        select(ConsumptionRecord.date)
        .where(ConsumptionRecord.user_id == user_id)
        .order_by(ConsumptionRecord.date.desc())
    ).first()
    if latest is None:
        today = date.today()
        return today.year, today.month
    return latest.year, latest.month


@router.get("/dashboard")
def dashboard_page(
    request: Request,
    year: int | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    assert current_user.id is not None
    default_year, default_month = _default_year_month(session, current_user.id)
    selected_year = year or default_year
    selected_month = month or default_month
    locale = getattr(request.state, "locale", "en")
    csrf_token = generate_csrf_token()

    response = render(
        request,
        "dashboard/month.html",
        {
            "current_user": current_user,
            "csrf_token": csrf_token,
            "year": selected_year,
            "month": selected_month,
            "month_label": format_date(
                date(selected_year, selected_month, 1), format="MMMM y", locale=locale
            ),
            "available_years": _available_years(session, current_user.id) or [selected_year],
        },
    )
    issue_csrf_cookie(response, csrf_token)
    return response


@router.get("/dashboard/annual")
def annual_dashboard_page(
    request: Request,
    year: int | None = Query(None),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    assert current_user.id is not None
    default_year, _ = _default_year_month(session, current_user.id)
    selected_year = year or default_year
    csrf_token = generate_csrf_token()

    response = render(
        request,
        "dashboard/annual.html",
        {
            "current_user": current_user,
            "csrf_token": csrf_token,
            "year": selected_year,
            "available_years": _available_years(session, current_user.id) or [selected_year],
        },
    )
    issue_csrf_cookie(response, csrf_token)
    return response


@router.get("/partials/dashboard/kpis")
def kpis_partial(
    request: Request,
    year: int = Query(...),
    month: int | None = Query(None, ge=1, le=12),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    assert current_user.id is not None
    if month is not None:
        summary = get_month_summary(session, current_user.id, year, month)
        response = render(request, "partials/dashboard/kpis.html", {"summary": summary})
        # Override htmx's default push-url (the partial's own URL) with the shareable page URL.
        response.headers["HX-Push-Url"] = f"/dashboard?year={year}&month={month}"
        return response

    locale = getattr(request.state, "locale", "en")
    annual_summary = get_annual_summary(session, current_user.id, year)
    max_month_label = (
        format_date(date(year, annual_summary.max_month.month, 1), format="MMMM", locale=locale)
        if annual_summary.max_month
        else None
    )
    min_month_label = (
        format_date(date(year, annual_summary.min_month.month, 1), format="MMMM", locale=locale)
        if annual_summary.min_month
        else None
    )
    response = render(
        request,
        "partials/dashboard/annual_kpis.html",
        {
            "summary": annual_summary,
            "max_month_label": max_month_label,
            "min_month_label": min_month_label,
        },
    )
    response.headers["HX-Push-Url"] = f"/dashboard/annual?year={year}"
    return response


@router.get("/partials/dashboard/daily-chart")
def daily_chart_partial(
    request: Request,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    assert current_user.id is not None
    summary = get_month_summary(session, current_user.id, year, month)
    t = get_request_translator(request)
    option = chart_options.daily_chart_option(summary, t)
    return render(request, "partials/dashboard/echart.html", {"option": option})


@router.get("/partials/dashboard/split-pie")
def split_pie_partial(
    request: Request,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    assert current_user.id is not None
    summary = get_month_summary(session, current_user.id, year, month)
    t = get_request_translator(request)
    option = chart_options.split_pie_option(summary, t)
    return render(request, "partials/dashboard/echart.html", {"option": option})


@router.get("/partials/dashboard/month-comparison")
def month_comparison_partial(
    request: Request,
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    assert current_user.id is not None
    summary = get_month_summary(session, current_user.id, year, month)
    t = get_request_translator(request)
    option = chart_options.month_comparison_option(summary, t)
    return render(request, "partials/dashboard/echart.html", {"option": option})


@router.get("/partials/dashboard/monthly-summary")
def monthly_summary_partial(
    request: Request,
    year: int = Query(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    assert current_user.id is not None
    summary = get_annual_summary(session, current_user.id, year)
    forecast = compute_forecast(session, current_user.id, year)
    t = get_request_translator(request)
    locale = getattr(request.state, "locale", "en")
    option = chart_options.monthly_summary_option(summary, forecast, t, locale)
    return render(
        request,
        "partials/dashboard/echart.html",
        {"option": option, "height_class": "h-[32rem] w-full"},
    )


@router.get("/partials/dashboard/cumulative")
def cumulative_partial(
    request: Request,
    year: int = Query(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    assert current_user.id is not None
    summary = get_annual_summary(session, current_user.id, year)
    forecast = compute_forecast(session, current_user.id, year)
    t = get_request_translator(request)
    locale = getattr(request.state, "locale", "en")
    option = chart_options.cumulative_option(summary, forecast, t, locale)
    return render(request, "partials/dashboard/echart.html", {"option": option})


@router.get("/partials/dashboard/season-split")
def season_split_partial(
    request: Request,
    year: int = Query(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    assert current_user.id is not None
    summary = get_annual_summary(session, current_user.id, year)
    forecast = compute_forecast(session, current_user.id, year)
    t = get_request_translator(request)
    option = chart_options.season_split_option(summary, forecast, t)
    return render(request, "partials/dashboard/echart.html", {"option": option})


@router.get("/partials/dashboard/calendar-heatmap")
def calendar_heatmap_partial(
    request: Request,
    year: int = Query(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    assert current_user.id is not None
    summary = get_annual_summary(session, current_user.id, year)
    option = chart_options.calendar_heatmap_option(summary, year)
    return render(
        request,
        "partials/dashboard/echart.html",
        {"option": option, "height_class": "h-56 w-full min-w-[700px]"},
    )
