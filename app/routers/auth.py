"""Login/logout and the post-login landing page.

See docs/04-auth.md and docs/05-api-routes.md.
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlmodel import Session, select

from app.core.deps import get_current_user
from app.core.rate_limit import (
    clear_failed_attempts,
    failed_attempt_cooldown_remaining,
    is_rate_limited,
    record_attempt,
    record_failed_attempt,
)
from app.core.security import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    generate_csrf_token,
    issue_csrf_cookie,
    issue_session_cookie,
    verify_csrf,
    verify_password_constant_time,
)
from app.core.templates import render
from app.db.models import User
from app.db.session import get_session

router = APIRouter()


@router.get("/login")
def login_page(request: Request) -> Response:
    csrf_token = generate_csrf_token()
    response = render(request, "login.html", {"csrf_token": csrf_token})
    issue_csrf_cookie(response, csrf_token)
    return response


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    client_ip = request.client.host if request.client else "unknown"
    if is_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    record_attempt(client_ip)

    cooldown_remaining = failed_attempt_cooldown_remaining(client_ip)
    if cooldown_remaining:
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(cooldown_remaining)},
        )

    cookie_csrf = request.cookies.get(CSRF_COOKIE_NAME)
    csrf_valid = verify_csrf(cookie_csrf, csrf_token)
    user = session.exec(select(User).where(User.username == username)).first()

    # Always run a real argon2 verify (even for an unknown user) so response time doesn't
    # leak whether the username exists.
    password_ok = verify_password_constant_time(password, user.password_hash if user else None)
    valid = csrf_valid and user is not None and user.is_active and password_ok
    if not valid:
        if csrf_valid:
            record_failed_attempt(client_ip)
        new_csrf_token = generate_csrf_token()
        response = render(
            request, "login.html", {"csrf_token": new_csrf_token, "error": True}, status_code=401
        )
        issue_csrf_cookie(response, new_csrf_token)
        return response

    assert user is not None and user.id is not None
    clear_failed_attempts(client_ip)
    response = RedirectResponse(url="/", status_code=303)
    issue_session_cookie(response, user.id)
    response.delete_cookie(CSRF_COOKIE_NAME)
    return response


@router.post("/logout")
def logout(
    request: Request,
    csrf_token: str = Form(...),
    current_user: User = Depends(get_current_user),
) -> Response:
    if not verify_csrf(request.cookies.get(CSRF_COOKIE_NAME), csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/")
def home(current_user: User = Depends(get_current_user)) -> Response:
    return RedirectResponse(url="/dashboard", status_code=303)
