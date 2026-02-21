"""
AI Service — advisory layer only.

Contract:
  - Receives plain dict with lead features
  - Returns AIAnalysisResult (score + recommendation + reason)
  - NEVER modifies lead state
  - NEVER makes business decisions
  - Score is a SIGNAL, not a gate — gates live in TransferService
"""
import json
import logging
from datetime import datetime, UTC

from openai import AsyncOpenAI

from app.core.config import settings
from app.schemas.lead import AIAnalysisResult
from app.ai.prompts import LEAD_ANALYSIS_SYSTEM_PROMPT, build_lead_analysis_prompt
from app.models.lead import Lead

logger = logging.getLogger(__name__)


class AIServiceError(Exception):
    pass


class AIService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    def _build_features(self, lead: Lead) -> dict:
        """
        Extract only the features we expose to AI.
        Explicit about what AI sees — no leaking of internal IDs or raw DB state.
        """
        days_since_created = (datetime.now(UTC) - lead.created_at).days
        return {
            "source": lead.source.value,
            "stage": lead.stage.value,
            "message_count": lead.message_count,
            "has_business_domain": lead.business_domain is not None,
            "business_domain": lead.business_domain.value if lead.business_domain else None,
            "days_since_created": days_since_created,
        }

    async def analyze_lead(self, lead: Lead) -> AIAnalysisResult:
        """
        Call LLM and return structured analysis.
        Raises AIServiceError on failure so caller can handle gracefully.
        """
        features = self._build_features(lead)
        prompt = build_lead_analysis_prompt(features)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": LEAD_ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,  # Low temp for consistent scoring
                max_tokens=256,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            logger.error(f"OpenAI API error for lead {lead.id}: {e}")
            raise AIServiceError(f"AI service unavailable: {e}") from e

        raw = response.choices[0].message.content
        try:
            data = json.loads(raw)
            return AIAnalysisResult(
                score=float(data["score"]),
                recommendation=str(data["recommendation"]),
                reason=str(data["reason"]),
            )
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            logger.error(f"AI response parse error: {raw!r} — {e}")
            raise AIServiceError(f"Invalid AI response format: {e}") from e
