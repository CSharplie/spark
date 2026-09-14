"""spark-cli: account management (see docs/04-auth.md). No public signup route."""

import typer
from sqlmodel import Session, select

from app.core.security import hash_password
from app.db import session as db_session
from app.db.models import User

app = typer.Typer(help="Manage Spark user accounts.")

MIN_PASSWORD_LENGTH = 12


@app.callback()
def _ensure_schema() -> None:
    """Ensure the schema exists before running any command (dev convenience)."""
    db_session.init_db()


def _check_password_length(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        typer.secho(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", fg=typer.colors.RED
        )
        raise typer.Exit(code=1)


def _get_password(password: str | None) -> str:
    if password is not None:
        return password

    try:
        return typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    except UnicodeDecodeError:
        typer.secho(
            "Unable to decode terminal input as UTF-8. Retry and type the password manually.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1) from None


@app.command("create-user")
def create_user(
    username: str = typer.Option(..., "--username", prompt=True),
    password: str | None = typer.Option(None, "--password"),
) -> None:
    """Create a new account. No public signup route exists — this is the only way in."""
    password = _get_password(password)
    _check_password_length(password)

    with Session(db_session.engine) as session:
        existing = session.exec(select(User).where(User.username == username)).first()
        if existing is not None:
            typer.secho(f"Username '{username}' already exists.", fg=typer.colors.RED)
            raise typer.Exit(code=1)

        user = User(username=username, password_hash=hash_password(password))
        session.add(user)
        session.commit()
        typer.secho(f"User '{username}' created.", fg=typer.colors.GREEN)


@app.command("list-users")
def list_users() -> None:
    with Session(db_session.engine) as session:
        users = session.exec(select(User)).all()
        if not users:
            typer.echo("No users found.")
            return
        for user in users:
            state = "active" if user.is_active else "inactive"
            typer.echo(f"{user.id}\t{user.username}\t{state}\t{user.created_at:%Y-%m-%d}")


@app.command("deactivate-user")
def deactivate_user(username: str = typer.Option(..., "--username")) -> None:
    with Session(db_session.engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if user is None:
            typer.secho(f"Username '{username}' not found.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        user.is_active = False
        session.add(user)
        session.commit()
        typer.secho(f"User '{username}' deactivated.", fg=typer.colors.GREEN)


@app.command("reset-password")
def reset_password(
    username: str = typer.Option(..., "--username"),
    password: str | None = typer.Option(None, "--password"),
) -> None:
    password = _get_password(password)
    _check_password_length(password)

    with Session(db_session.engine) as session:
        user = session.exec(select(User).where(User.username == username)).first()
        if user is None:
            typer.secho(f"Username '{username}' not found.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
        user.password_hash = hash_password(password)
        session.add(user)
        session.commit()
        typer.secho(f"Password reset for '{username}'.", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
