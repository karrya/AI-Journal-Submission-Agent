import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.schemas.common import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("/ready", response_model=HealthResponse)
def readiness(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("Database readiness check failed (%s)", type(exc).__name__)
        raise AppError(
            status_code=503,
            code="DATABASE_UNAVAILABLE",
            message="数据库暂不可用",
        ) from None
    return {"status": "ok"}
