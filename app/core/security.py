"""Password hashing, JWT session tokens, and CSRF helpers."""

import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from starlette.responses import Response

from app.core.config import get_settings

_hasher = PasswordHasher()

JWT_ALGORITHM = "HS256"
SESSION_COOKIE_NAME = "session"
CSRF_COOKIE_NAME = "csrf_token"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


# Precomputed so an unknown-username login still pays the same argon2 cost as a real one —
# otherwise the response time difference lets an attacker enumerate valid usernames.
_DUMMY_PASSWORD_HASH = _hasher.hash(secrets.token_urlsafe(32))


def verify_password_constant_time(password: str, password_hash: str | None) -> bool:
    """Like verify_password, but always does real argon2 work even when `password_hash`
    is None (unknown user), to avoid a timing side-channel for username enumeration."""
    try:
        matches = _hasher.verify(password_hash or _DUMMY_PASSWORD_HASH, password)
        return matches and password_hash is not None
    except VerifyMismatchError:
        return False


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """Return the user id encoded in the token, or None if invalid/expired."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf(cookie_value: str | None, form_value: str | None) -> bool:
    """Double-submit CSRF check: cookie and form field must match and be non-empty."""
    if not cookie_value or not form_value:
        return False
    return secrets.compare_digest(cookie_value, form_value)


def issue_csrf_cookie(response: Response, token: str) -> None:
    """Set `token` as the CSRF cookie on `response` (caller renders the template with the
    same token first, then sets the cookie on the resulting response)."""
    settings = get_settings()
    response.set_cookie(
        CSRF_COOKIE_NAME, token, httponly=True, secure=settings.is_production, samesite="lax"
    )


def issue_session_cookie(response: Response, user_id: int) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_access_token(user_id),
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.jwt_expire_minutes * 60,
    )
