from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")
    app_name: str = "Academic Submission Agent"
    environment: str = "development"
    database_url: str = "mysql+pymysql://unset:unset@127.0.0.1/unset"
    alembic_database_url: str | None = None
    test_database_url: str | None = None
    csrf_secret_key: str = ""
    allowed_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    session_idle_minutes: int = Field(default=30, gt=0)
    session_absolute_hours: int = Field(default=8, gt=0)
    session_cookie_secure: bool | None = None
    max_upload_bytes: int = Field(default=100 * 1024 * 1024, le=500 * 1024 * 1024)
    storage_root: str = str(PROJECT_ROOT / "storage")


@lru_cache
def get_settings() -> Settings:
    return Settings()
