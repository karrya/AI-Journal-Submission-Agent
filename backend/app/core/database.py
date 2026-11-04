from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def create_mysql_engine(database_url: str) -> Engine:
    if not make_url(database_url).drivername.startswith("mysql+"):
        raise ValueError("a MySQL database URL is required")
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=280,
        connect_args={"init_command": "SET time_zone = '+00:00'"},
    )


engine = create_mysql_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
