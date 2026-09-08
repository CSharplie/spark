"""Application configuration, read from environment variables / .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPARK_", env_file=".env", extra="ignore")

    env: str = "development"  # "development" | "production" — controls cookie Secure flag
    secret_key: str = "insecure-dev-secret-change-me-32-bytes-min"  # override via SPARK_SECRET_KEY
    database_path: str = "data/spark.db"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days
    co2_factor_g_per_kwh: float = 52.0  # French grid average, adjustable

    @property
    def database_url(self) -> str:
        db_path = BASE_DIR / self.database_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path}"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
