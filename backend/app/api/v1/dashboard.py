from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal
from app.core.database import get_db
from app.schemas.audit import DashboardSummary
from app.services.dashboard import DashboardService
from app.services.permissions import require_roles

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[
        Principal, Depends(require_roles("submission_operator", "reviewer"))
    ],
) -> DashboardSummary:
    return DashboardService(db, principal.user, request.state.request_id).summary()
