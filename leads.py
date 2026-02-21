from fastapi import APIRouter, Depends, HTTPException, Query
from starlette import status

from app.core.deps import get_lead_service, get_transfer_service
from app.models.lead import ColdStage
from app.schemas.lead import (
    LeadCreate,
    LeadResponse,
    LeadListResponse,
    LeadStageUpdate,
    LeadMessageUpdate,
    AIAnalysisResult,
)
from app.schemas.sale import SaleResponse
from app.services.lead_service import LeadService, LeadNotFoundError, LeadStageError
from app.services.transfer_service import TransferService, TransferError
from app.ai.ai_service import AIServiceError

router = APIRouter()


def _not_found(lead_id: int):
    raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")


def _bad_request(msg: str):
    raise HTTPException(status_code=400, detail=msg)


# ──────────────────────────────────────────────
# CRUD
# ──────────────────────────────────────────────

@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    data: LeadCreate,
    svc: LeadService = Depends(get_lead_service),
):
    """Create a new lead. Source is required; business_domain is optional."""
    lead = await svc.create_lead(data)
    return lead


@router.get("", response_model=LeadListResponse)
async def list_leads(
    stage: ColdStage | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    svc: LeadService = Depends(get_lead_service),
):
    items, total = await svc.get_leads(stage=stage, offset=offset, limit=limit)
    return {"items": items, "total": total}


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: int,
    svc: LeadService = Depends(get_lead_service),
):
    try:
        return await svc.get_lead(lead_id)
    except LeadNotFoundError:
        _not_found(lead_id)


# ──────────────────────────────────────────────
# Stage management
# ──────────────────────────────────────────────

@router.patch("/{lead_id}/stage", response_model=LeadResponse)
async def update_stage(
    lead_id: int,
    data: LeadStageUpdate,
    svc: LeadService = Depends(get_lead_service),
):
    """
    Advance lead to next stage.
    Rules: sequential only, terminal stages locked.
    """
    try:
        lead = await svc.get_lead(lead_id)
        return await svc.transition_stage(lead, data.stage)
    except LeadNotFoundError:
        _not_found(lead_id)
    except LeadStageError as e:
        _bad_request(str(e))


@router.post("/{lead_id}/messages", response_model=LeadResponse)
async def record_messages(
    lead_id: int,
    data: LeadMessageUpdate,
    svc: LeadService = Depends(get_lead_service),
):
    """Increment message counter for activity tracking."""
    try:
        lead = await svc.get_lead(lead_id)
        return await svc.increment_messages(lead, data.increment)
    except LeadNotFoundError:
        _not_found(lead_id)


# ──────────────────────────────────────────────
# AI analysis
# ──────────────────────────────────────────────

@router.post("/{lead_id}/analyze", response_model=AIAnalysisResult)
async def analyze_lead(
    lead_id: int,
    svc: LeadService = Depends(get_lead_service),
    transfer_svc: TransferService = Depends(get_transfer_service),
):
    """
    Request AI analysis of lead.
    Returns score + recommendation. Does NOT change lead stage.
    Manager reviews the recommendation and decides next action.
    """
    try:
        lead = await svc.get_lead(lead_id)
        return await transfer_svc.analyze_lead(lead)
    except LeadNotFoundError:
        _not_found(lead_id)
    except AIServiceError as e:
        raise HTTPException(status_code=503, detail=f"AI service error: {e}")


# ──────────────────────────────────────────────
# Transfer to sales
# ──────────────────────────────────────────────

@router.post("/{lead_id}/transfer", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
async def transfer_lead(
    lead_id: int,
    svc: LeadService = Depends(get_lead_service),
    transfer_svc: TransferService = Depends(get_transfer_service),
):
    """
    Transfer qualified lead to sales pipeline.

    Requirements (enforced server-side):
    - AI score >= 0.6
    - Business domain must be set
    - Lead must not be already transferred

    This endpoint is intentionally separate from stage update —
    it's a significant business action with multiple gates.
    """
    try:
        lead = await svc.get_lead(lead_id)
        _, sale = await transfer_svc.transfer_to_sales(lead)
        return sale
    except LeadNotFoundError:
        _not_found(lead_id)
    except TransferError as e:
        _bad_request(str(e))
