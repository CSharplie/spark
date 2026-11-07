"""Shared FastAPI dependencies."""

from collections.abc import Iterator

import httpx
from fastapi import Depends
from sqlmodel import Session
from starlette.requests import Request

from app.core.exceptions import NotAuthenticated
from app.core.security import SESSION_COOKIE_NAME, decode_access_token
from app.db.models import User
from app.db.session import get_session


def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user_id = decode_access_token(token) if token else None
    if user_id is None:
        raise NotAuthenticated()

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise NotAuthenticated()
    return user


def get_http_client() -> Iterator[httpx.Client]:
    with httpx.Client(timeout=15.0) as client:
        yield client
