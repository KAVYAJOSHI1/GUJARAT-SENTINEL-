"""
AI Investigation Agent + gap detection API (Phase 14 §7, §8, §10).

  POST /ai/investigation/run       multi-step, tool-planned investigation report
  GET  /ai/investigation/gaps      evidence / coverage gaps for one plate

Both JWT-authenticated and READ-ONLY. The agent can only call tools in its
strict registry (all bounded SELECTs); it never writes, never generates
SQL, never creates alerts. `run` is audited.
"""
from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from sqlmodel import Session

from app.api.deps import get_current_user
from app.config import settings
from app.core.exceptions import SentinelException
from app.database import get_db
from app.schemas.ai import AgentRunRequest, AgentRunResponse, GapDetectionResponse
from app.schemas.auth import CurrentUser
from app.services.ai.agent import InvestigationAgentService
from app.services.ai.gaps import InvestigationGapService
from app.services.audit import client_ip, record_audit
from app.services.plate_utils import normalize_plate

router = APIRouter()


@router.post("/run", response_model=AgentRunResponse)
async def run_investigation(
    body: AgentRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    if not settings.AI_AGENT_ENABLED:
        raise SentinelException("AGENT_DISABLED", "The investigation agent is disabled.", 503)

    report = await run_in_threadpool(
        InvestigationAgentService(db).run, body.query, context_plate=body.plate
    )
    record_audit(
        db, action="AI_INVESTIGATION_AGENT", user_id=user.id, resource="vehicle",
        resource_id=report.get("plate"), ip_address=client_ip(request),
        detail={"steps": len(report.get("steps", [])),
                "plan_source": report.get("plan_source"),
                "gaps": len(report.get("gaps", []))},
    )
    return AgentRunResponse(**report)


@router.get("/gaps", response_model=GapDetectionResponse)
def investigation_gaps(
    plate: str = Query(..., min_length=3),
    db: Session = Depends(get_db),
    _: CurrentUser = Depends(get_current_user),
):
    return GapDetectionResponse(**InvestigationGapService(db).detect(normalize_plate(plate)))
