"""
Command Center API (Phase 16A).

  GET /api/v1/command-center/summary

One bounded, read-only aggregation for the /command-center landing page.
JWT-authenticated. Composed from existing services -- no new business
logic, no video processing.
"""
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.schemas.auth import CurrentUser
from app.services.command_center import command_center_summary

router = APIRouter()


@router.get("/summary")
def summary(
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    return command_center_summary(db)
