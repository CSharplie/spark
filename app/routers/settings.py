"""Settings page: city configuration and daily temperature download.

See docs/05-api-routes.md.
"""

from typing import Any

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import Response
from sqlmodel import Session

from app.core.deps import get_current_user, get_http_client
from app.core.security import (
    CSRF_COOKIE_NAME,
    generate_csrf_token,
    issue_csrf_cookie,
    verify_csrf,
)
from app.core.templates import render
from app.db.models import User
from app.db.session import get_session
from app.services.weather import (
    geocode_city,
    set_location,
    sync_temperatures,
    temperature_coverage,
)

router = APIRouter()

MAX_CITY_LENGTH = 100


def _panel_context(session: Session, user: User) -> dict[str, Any]:
    assert user.id is not None
    temperature_days, consumption_days = temperature_coverage(session, user.id)
    return {
        "current_user": user,
        "temperature_days": temperature_days,
        "consumption_days": consumption_days,
    }


def _panel(
    request: Request,
    session: Session,
    user: User,
    message_key: str,
    level: str = "success",
    **message_args: object,
) -> Response:
    # Only #settings-panel is swapped, so the visible forms' CSRF token must stay valid.
    return render(
        request,
        "partials/settings_panel.html",
        {
            **_panel_context(session, user),
            "message_key": message_key,
            "message_level": level,
            "message_args": message_args,
        },
    )


def _check_csrf(request: Request, csrf_token: str) -> None:
    if not verify_csrf(request.cookies.get(CSRF_COOKIE_NAME), csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


@router.get("/settings")
def settings_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    csrf_token = generate_csrf_token()
    response = render(
        request,
        "settings.html",
        {"csrf_token": csrf_token, **_panel_context(session, current_user)},
    )
    issue_csrf_cookie(response, csrf_token)
    return response


@router.post("/settings/city")
def update_city(
    request: Request,
    city: str = Form(...),
    csrf_token: str = Form(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    client: httpx.Client = Depends(get_http_client),
) -> Response:
    _check_csrf(request, csrf_token)
    query = city.strip()
    if not query or len(query) > MAX_CITY_LENGTH:
        return _panel(request, session, current_user, "settings.city.invalid", "error")

    try:
        location = geocode_city(client, query)
        if location is None:
            return _panel(
                request, session, current_user, "settings.city.not_found", "error", city=query
            )
        set_location(session, current_user, location)
        result = sync_temperatures(session, current_user, client)
    except httpx.HTTPError:
        return _panel(request, session, current_user, "settings.weather.unavailable", "error")

    return _panel(
        request,
        session,
        current_user,
        "settings.temperatures.synced",
        fetched=result.fetched,
        missing=result.missing,
    )


@router.post("/settings/temperatures/sync")
def sync_temperatures_route(
    request: Request,
    csrf_token: str = Form(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    client: httpx.Client = Depends(get_http_client),
) -> Response:
    _check_csrf(request, csrf_token)
    if current_user.latitude is None or current_user.longitude is None:
        return _panel(request, session, current_user, "settings.temperatures.no_city", "error")

    try:
        result = sync_temperatures(session, current_user, client)
    except httpx.HTTPError:
        return _panel(request, session, current_user, "settings.weather.unavailable", "error")

    return _panel(
        request,
        session,
        current_user,
        "settings.temperatures.synced",
        fetched=result.fetched,
        missing=result.missing,
    )
