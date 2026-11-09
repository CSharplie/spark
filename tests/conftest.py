"""Shared pytest fixtures: isolated temp SQLite DB + httpx AsyncClient."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import Session, SQLModel, create_engine

import app.db.session as db_session
from app.core import rate_limit
from app.core.security import hash_password
from app.db.models import User


@pytest.fixture(autouse=True)
def _reset_login_rate_limit() -> None:
    rate_limit._attempts.clear()
    rate_limit._failed_attempts.clear()
    rate_limit._failure_cooldowns.clear()


@pytest.fixture
def engine(tmp_path, monkeypatch):
    """A fresh SQLite file per test, wired into app.db.session.engine."""
    test_engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(test_engine)
    monkeypatch.setattr(db_session, "engine", test_engine)
    return test_engine


@pytest.fixture
def session(engine) -> Session:
    with Session(engine) as session:
        yield session


@pytest.fixture
def test_user(session: Session) -> User:
    user = User(username="alice", password_hash=hash_password("correct-horse-battery"))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
async def client(engine) -> AsyncIterator[AsyncClient]:
    from app.main import app as fastapi_app

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
