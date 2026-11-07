"""Jinja2 rendering helper — injects the active-locale translator into every template."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from starlette.requests import Request
from starlette.templating import _TemplateResponse

from app.i18n import DEFAULT_LOCALE, get_translator

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


def _tojson(value: Any) -> Markup:
    """JSON-encode `value` for safe embedding inside an HTML attribute (single-quoted)."""
    encoded = (
        json.dumps(value)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("'", "\\u0027")
    )
    return Markup(encoded)  # noqa: S704 — JSON-safe encoded above, not raw HTML


templates.env.filters["tojson"] = _tojson


def get_request_translator(request: Request) -> Callable[..., str]:
    locale = getattr(request.state, "locale", DEFAULT_LOCALE)
    return get_translator(locale)


def render(
    request: Request, name: str, context: dict[str, Any] | None = None, status_code: int = 200
) -> _TemplateResponse:
    locale = getattr(request.state, "locale", DEFAULT_LOCALE)
    merged = {
        "t": get_translator(locale),
        "locale": locale,
        **(context or {}),
    }
    return templates.TemplateResponse(request, name, merged, status_code=status_code)
