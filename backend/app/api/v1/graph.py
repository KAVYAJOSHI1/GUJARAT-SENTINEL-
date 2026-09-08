"""
Investigation Graph API (Phase 14 §12, §10).

  GET /ai/graph?plate=GJ18TC0450

Deterministic graph built only from persisted relational rows. Read-only,
JWT-authenticated, bounded. Every node carries an `href` to its Sentinel
entity page.
"""
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.schemas.auth import CurrentUser
from app.schemas.graph import InvestigationGraph
from app.services.ai.graph import InvestigationGraphService
from app.services.plate_utils import normalize_plate

router = APIRouter()


@router.get("", response_model=InvestigationGraph)
def investigation_graph(
    plate: str = Query(..., min_length=3),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    return InvestigationGraph(
        **InvestigationGraphService(db).build_for_plate(normalize_plate(plate))
    )
