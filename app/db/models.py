"""SQLModel table definitions — see docs/02-data-model.md for the schema."""

from datetime import UTC, datetime
from datetime import date as date_

from sqlmodel import Field, SQLModel, UniqueConstraint


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    __tablename__ = "user"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=_utcnow)


class ImportBatch(SQLModel, table=True):
    __tablename__ = "import_batch"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    source_filename: str
    imported_at: datetime = Field(default_factory=_utcnow)
    row_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    status: str = "success"  # "success" | "partial" | "failed"
    error_message: str | None = None


class ConsumptionRecord(SQLModel, table=True):
    __tablename__ = "consumption_record"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_consumption_user_date"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    import_batch_id: int = Field(foreign_key="import_batch.id")
    date: date_
    peak_hours_kwh: float
    off_peak_hours_kwh: float
    total_kwh: float
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
