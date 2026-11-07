"""FastAPI application factory — see docs/01-architecture.md."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings
from app.core.exceptions import NotAuthenticated
from app.i18n.middleware import LocaleMiddleware
from app.routers import auth, dashboard, imports
from app.routers import settings as settings_router

STATIC_DIR = Path(__file__).resolve().parent / "static"
settings = get_settings()

app = FastAPI(
    title="Spark",
    # No public API consumers — close off the interactive docs/schema in production
    # to reduce attack-surface disclosure; keep them in dev for convenience.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.add_middleware(LocaleMiddleware)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(imports.router)
app.include_router(settings_router.router)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "  # ECharts injects inline-styled tooltip elements
        "img-src 'self' data:; "
        "base-uri 'self'; "
        "frame-ancestors 'none'"
    )
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(_request: Request, _exc: NotAuthenticated) -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def run() -> None:
    """Entry point for the `spark` console script (dev server)."""
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
