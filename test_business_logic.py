"""
Unit tests for core business logic — no DB or AI calls needed.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, UTC

from app.models.lead import Lead, ColdStage, LeadSource, BusinessDomain
from app.models.sale import Sale, SaleStage
from app.services.lead_service import LeadService, LeadStageError
from app.services.transfer_service import TransferService, TransferError
from app.schemas.lead import AIAnalysisResult


def make_lead(**kwargs) -> Lead:
    defaults = dict(
        id=1,
        source=LeadSource.PARTNER,
        stage=ColdStage.NEW,
        business_domain=None,
        message_count=0,
        ai_score=None,
        ai_recommendation=None,
        ai_reason=None,
        ai_analyzed_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    lead = Lead(**{**defaults, **kwargs})
    return lead


# ──────────────────────────────────────────────
# Stage transition tests
# ──────────────────────────────────────────────

class TestLeadStageTransitions:
    @pytest.mark.asyncio
    async def test_valid_sequential_transition(self):
        repo = AsyncMock()
        repo.save = AsyncMock(side_effect=lambda x: x)
        svc = LeadService(repo)
        lead = make_lead(stage=ColdStage.NEW)

        result = await svc.transition_stage(lead, ColdStage.CONTACTED)
        assert result.stage == ColdStage.CONTACTED

    @pytest.mark.asyncio
    async def test_skip_stage_raises_error(self):
        repo = AsyncMock()
        svc = LeadService(repo)
        lead = make_lead(stage=ColdStage.NEW)

        with pytest.raises(LeadStageError, match="Expected next stage"):
            await svc.transition_stage(lead, ColdStage.QUALIFIED)

    @pytest.mark.asyncio
    async def test_terminal_transferred_cannot_change(self):
        repo = AsyncMock()
        svc = LeadService(repo)
        lead = make_lead(stage=ColdStage.TRANSFERRED)

        with pytest.raises(LeadStageError, match="terminal stage"):
            await svc.transition_stage(lead, ColdStage.LOST)

    @pytest.mark.asyncio
    async def test_lost_allowed_from_any_stage(self):
        repo = AsyncMock()
        repo.save = AsyncMock(side_effect=lambda x: x)
        svc = LeadService(repo)
        lead = make_lead(stage=ColdStage.CONTACTED)

        result = await svc.transition_stage(lead, ColdStage.LOST)
        assert result.stage == ColdStage.LOST


# ──────────────────────────────────────────────
# Transfer gate tests
# ──────────────────────────────────────────────

class TestTransferGates:
    def _make_transfer_svc(self, ai_score=0.75):
        lead_repo = AsyncMock()
        lead_repo.save = AsyncMock(side_effect=lambda x: x)
        sale_repo = AsyncMock()
        sale_repo.create = AsyncMock(return_value=Sale(
            id=1, lead_id=1, stage=SaleStage.NEW,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC)
        ))
        ai_service = AsyncMock()
        ai_service.analyze_lead = AsyncMock(return_value=AIAnalysisResult(
            score=ai_score, recommendation="transfer_to_sales", reason="test"
        ))
        return TransferService(lead_repo, sale_repo, ai_service)

    @pytest.mark.asyncio
    async def test_transfer_succeeds_with_valid_lead(self):
        svc = self._make_transfer_svc(ai_score=0.75)
        lead = make_lead(
            stage=ColdStage.QUALIFIED,
            business_domain=BusinessDomain.FIRST,
            ai_score=0.75,
            ai_recommendation="transfer_to_sales",
            ai_reason="test",
            ai_analyzed_at=datetime.now(UTC),
        )
        _, sale = await svc.transfer_to_sales(lead)
        assert sale.stage == SaleStage.NEW

    @pytest.mark.asyncio
    async def test_transfer_blocked_no_ai_score(self):
        svc = self._make_transfer_svc()
        lead = make_lead(
            stage=ColdStage.QUALIFIED,
            business_domain=BusinessDomain.FIRST,
            ai_score=None,
        )
        with pytest.raises(TransferError, match="AI analysis required"):
            await svc.transfer_to_sales(lead)

    @pytest.mark.asyncio
    async def test_transfer_blocked_low_score(self):
        svc = self._make_transfer_svc(ai_score=0.4)
        lead = make_lead(
            stage=ColdStage.QUALIFIED,
            business_domain=BusinessDomain.FIRST,
            ai_score=0.4,
            ai_recommendation="continue_nurturing",
            ai_reason="test",
            ai_analyzed_at=datetime.now(UTC),
        )
        with pytest.raises(TransferError, match="below minimum threshold"):
            await svc.transfer_to_sales(lead)

    @pytest.mark.asyncio
    async def test_transfer_blocked_no_domain(self):
        svc = self._make_transfer_svc()
        lead = make_lead(
            stage=ColdStage.QUALIFIED,
            business_domain=None,
            ai_score=0.9,
            ai_recommendation="transfer_to_sales",
            ai_reason="test",
            ai_analyzed_at=datetime.now(UTC),
        )
        with pytest.raises(TransferError, match="business_domain"):
            await svc.transfer_to_sales(lead)

    @pytest.mark.asyncio
    async def test_transfer_blocked_already_transferred(self):
        svc = self._make_transfer_svc()
        lead = make_lead(
            stage=ColdStage.TRANSFERRED,
            business_domain=BusinessDomain.FIRST,
            ai_score=0.9,
            ai_analyzed_at=datetime.now(UTC),
        )
        with pytest.raises(TransferError, match="already transferred"):
            await svc.transfer_to_sales(lead)
