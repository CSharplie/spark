"""Locale negotiation from the browser's Accept-Language header, else default."""

from collections.abc import Awaitable, Callable

from babel.core import negotiate_locale
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES


def resolve_locale(request: Request) -> str:
    accept_language = request.headers.get("accept-language", "")
    preferred = [
        lang.split(";")[0].strip().replace("-", "_") for lang in accept_language.split(",") if lang
    ]
    return negotiate_locale(preferred, SUPPORTED_LOCALES) or DEFAULT_LOCALE


class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.locale = resolve_locale(request)
        return await call_next(request)
