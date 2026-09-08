"""CLI user-management tests (see docs/04-auth.md)."""

from typer.testing import CliRunner

from app.cli.main import app
from app.core.security import verify_password
from app.db.models import User

runner = CliRunner()


def test_create_user_success(engine, session) -> None:
    result = runner.invoke(
        app,
        ["create-user", "--username", "bob", "--password", "a-strong-password-123"],
    )

    assert result.exit_code == 0, result.output
    assert "created" in result.output.lower()

    from sqlmodel import select

    user = session.exec(select(User).where(User.username == "bob")).first()
    assert user is not None
    assert verify_password("a-strong-password-123", user.password_hash)


def test_create_user_rejects_short_password(engine) -> None:
    result = runner.invoke(app, ["create-user", "--username", "bob", "--password", "short"])
    assert result.exit_code == 1
    assert "at least" in result.output.lower()


def test_create_user_rejects_duplicate_username(engine, test_user: User) -> None:
    result = runner.invoke(
        app,
        ["create-user", "--username", "alice", "--password", "a-strong-password-123"],
    )
    assert result.exit_code == 1
    assert "already exists" in result.output.lower()


def test_list_users(engine, test_user: User) -> None:
    result = runner.invoke(app, ["list-users"])
    assert result.exit_code == 0
    assert "alice" in result.output


def test_deactivate_user(engine, session, test_user: User) -> None:
    result = runner.invoke(app, ["deactivate-user", "--username", "alice"])
    assert result.exit_code == 0

    session.refresh(test_user)
    assert test_user.is_active is False
