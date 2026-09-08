"""SQLModel engine and session dependency."""

from collections.abc import Generator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


@event.listens_for(Engine, "connect")
def _enable_wal_mode(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db() -> None:
    """Create tables that don't exist yet (dev convenience; Alembic drives real migrations)."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session
