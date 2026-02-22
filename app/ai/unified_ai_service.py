"""
Unified AI Service - Combines Voice Processing and AI Assistant.
Provides free voice-to-text (local & API) and improved natural language understanding.
"""
import os
import re
import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Try to import faster-whisper for local transcription
try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    logger.warning("faster-whisper not installed. Install for local offline transcription.")


class UnifiedAIService:
    """
    Unified AI Service that handles:
    - Voice transcription (local or API - FREE & paid options)
    - Text command understanding
    - Lead queries
    - Note categorization
    
    Transcription priority:
    1. Local faster-whisper (FREE, offline, fastest)
    2. HuggingFace API (FREE, online)
    3. OpenAI Whisper (paid, reliable)
    """
    
    # Class-level model cache
    _whisper_model = None
    _model_loaded = False
    
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.huggingface_token = os.getenv("HUGGINGFACE_TOKEN")
        self.local_whisper_model = os.getenv("LOCAL_WHISPER_MODEL", "base")  # tiny, base, small
        self.api_base_url = "http://localhost:8000"
    
    # ==================== VOICE PROCESSING ====================
    
    async def transcribe_voice(self, voice_content: bytes) -> str | None:
        """
        Transcribe voice to text.
        Priority: Local (faster-whisper) > HuggingFace API > OpenAI API
        """
        # 1. Try local faster-whisper (FREE, offline, fastest)
        if FASTER_WHISPER_AVAILABLE:
            result = await self._transcribe_local(voice_content)
            if result:
                logger.info("Used local faster-whisper transcription")
                return result
        
        # 2. Try HuggingFace API (FREE, online)
        if self.huggingface_token:
            result = await self._transcribe_huggingface(voice_content)
            if result:
                logger.info("Used HuggingFace API transcription")
                return result
        
        # 3. Try OpenAI Whisper (paid, reliable)
        if self.openai_api_key:
            result = await self._transcribe_openai(voice_content)
            if result:
                logger.info("Used OpenAI Whisper transcription")
                return result
        
        logger.error("No voice transcription service available")
        return None
    
    async def _transcribe_local(self, voice_content: bytes) -> str | None:
        """Transcribe using local faster-whisper (FREE, offline)."""
        try:
            # Load model once and cache it
            if not UnifiedAIService._whisper_model:
                logger.info(f"Loading local Whisper model: {self.local_whisper_model}")
                UnifiedAIService._whisper_model = WhisperModel(
                    self.local_whisper_model, 
                    device="cpu", 
                    compute_type="int8"
                )
                UnifiedAIService._model_loaded = True
            
            # Save to temp file (faster-whisper needs file path)
            import tempfile
            import asyncio
            
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            
            def transcribe():
                with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
                    tmp.write(voice_content)
                    tmp_path = tmp.name
                
                try:
                    segments, info = UnifiedAIService._whisper_model.transcribe(
                        tmp_path,
                        beam_size=5,
                        vad_filter=True,
                        vad_parameters=dict(min_silence_duration_ms=500)
                    )
                    
                    full_text = ""
                    for segment in segments:
                        full_text += segment.text.strip() + " "
                    
                    return full_text.strip()
                finally:
                    os.unlink(tmp_path)
            
            result = await loop.run_in_executor(None, transcribe)
            return result if result else None
            
        except Exception as e:
            logger.warning(f"Local transcription failed: {e}")
            return None
    
    async def _transcribe_huggingface(self, voice_content: bytes) -> str | None:
        """Transcribe using HuggingFace Inference API (FREE)."""
        try:
            async with httpx.AsyncClient() as client:
                files = {"file": ("voice.ogg", voice_content, "audio/ogg")}
                data = {"model": "openai/whisper-base"}
                headers = {"Authorization": f"Bearer {self.huggingface_token}"}
                
                response = await client.post(
                    "https://api-inference.huggingface.co/models/openai/whisper-base",
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=30.0
                )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("text", "").strip()
            else:
                logger.warning(f"HuggingFace Whisper error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.warning(f"HuggingFace transcription failed: {e}")
            return None
    
    async def _transcribe_openai(self, voice_content: bytes) -> str | None:
        """Transcribe using OpenAI Whisper API (paid)."""
        if not self.openai_api_key:
            return None
            
        try:
            files = {"file": ("voice.ogg", voice_content, "audio/ogg")}
            headers = {"Authorization": f"Bearer {self.openai_api_key}"}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data={"model": "whisper-1"},
                    timeout=30.0
                )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("text", "").strip()
            else:
                logger.error(f"OpenAI Whisper error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"OpenAI transcription error: {e}")
            return None
    
    # ==================== COMMAND PARSING ====================
    
    def parse_command(self, text: str) -> dict:
        """Parse natural language text into structured command."""
        text_lower = text.lower()
        
        result = {
            "action": None,
            "query": None,
            "lead_data": {},
            "confidence": 0.5,
            "raw_text": text
        }
        
        # CREATE LEAD commands
        create_patterns = [
            "додай ліда", "додай новий ліда", "додай нового ліда",
            "створи ліда", "новий ліда", "створи нового ліда",
            "add lead", "create lead", "new lead", "add new lead"
        ]
        
        if any(p in text_lower for p in create_patterns):
            result["action"] = "create"
            result["lead_data"] = self._parse_lead_data(text)
            result["confidence"] = 0.9
            return result
        
        # SHOW LEADS / LIST commands
        list_patterns = [
            "покажи ліди", "покажи всіх лідів", "список лідів",
            "show leads", "show all leads", "list leads", "мої ліди"
        ]
        
        if any(p in text_lower for p in list_patterns):
            result["action"] = "list"
            result["confidence"] = 0.9
            return result
        
        # NOTES commands
        show_notes_patterns = [
            "покажи нотатки", "покажи замечания", "show notes", 
            "мої нотатки", "нотатки ліда"
        ]
        
        if any(p in text_lower for p in show_notes_patterns):
            result["action"] = "notes"
            result["confidence"] = 0.9
            return result
        
        # ADD NOTE commands
        note_patterns = [
            "додай нотатку", "додай замітку", "додай note",
            "запиши нотатку", "create note", "add note"
        ]
        
        if any(p in text_lower for p in note_patterns):
            lead_id = self._extract_lead_id(text)
            result["action"] = "note"
            result["lead_data"] = {"lead_id": lead_id, "content": text}
            result["confidence"] = 0.8
            return result
        
        # STATS commands
        stats_patterns = [
            "статистика", "звіти", "stats", "show stats",
            "дашборд", "dashboard", "покажи статистику"
        ]
        
        if any(p in text_lower for p in stats_patterns):
            result["action"] = "stats"
            result["confidence"] = 0.9
            return result
        
        # EDIT LEAD commands
        edit_patterns = [
            "редагуй ліда", "зміни ліда", "edit lead", "change lead",
            "онов ліда", "редагуй #", "зміни #"
        ]
        
        if any(p in text_lower for p in edit_patterns):
            lead_id = self._extract_lead_id(text)
            result["action"] = "edit"
            result["lead_data"] = {"lead_id": lead_id}
            result["confidence"] = 0.8
            return result
        
        # DELETE LEAD commands
        delete_patterns = [
            "видали ліда", "видалити ліда", "delete lead", "remove lead"
        ]
        
        if any(p in text_lower for p in delete_patterns):
            lead_id = self._extract_lead_id(text)
            result["action"] = "delete"
            result["lead_data"] = {"lead_id": lead_id}
            result["confidence"] = 0.8
            return result
        
        # SALES commands
        sales_patterns = [
            "продажі", "sales", "pipeline", "воронка",
            "покажи продажі", "show sales"
        ]
        
        if any(p in text_lower for p in sales_patterns):
            result["action"] = "sales"
            result["confidence"] = 0.9
            return result
        
        # Search queries
        search_patterns = ["знайди", "пошук", "search", "find", "шукай"]
        
        if any(p in text_lower for p in search_patterns):
            query = text
            for word in ["знайди", "пошук", "search", "find", "шукай"]:
                query = query.replace(word, "", 1).strip()
            if query and len(query) > 1:
                result["action"] = "search"
                result["query"] = query
                result["confidence"] = 0.7
                return result
        
        # Analysis queries
        analysis_patterns = [
            "хто найкращ", "хто найгаряч", "best lead", "hot lead",
            "аналіз", "analyze", "оціни", "score"
        ]
        
        if any(p in text_lower for p in analysis_patterns):
            result["action"] = "analyze"
            result["query"] = text
            result["confidence"] = 0.6
            return result
        
        # Unknown - use as AI query
        result["action"] = "ai_query"
        result["query"] = text
        result["confidence"] = 0.4
        
        return result
    
    def _extract_lead_id(self, text: str) -> int | None:
        """Extract lead ID from text."""
        patterns = [
            r'лід\s*#?(\d+)',
            r'lead\s*#?(\d+)',
            r'до\s*лід[ау]\s*#?(\d+)',
            r'для\s*лід[ау]\s*#?(\d+)',
            r'#(\d+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                try:
                    return int(match.group(1))
                except:
                    pass
        return None
    
    def _parse_lead_data(self, text: str) -> dict:
        """Parse lead data from text/voice input."""
        text_lower = text.lower()
        
        result = {
            "name": None,
            "phone": None,
            "email": None,
            "source": "MANUAL",
            "domain": None
        }
        
        # Extract name
        name_patterns = [
            r'лід[ау]?[.,]?\s*([А-Яа-яёЇїІіЄєA-Za-z]+(?:\s+[А-Яа-яёЇїІіЄєA-Za-z]+(?:\s+[А-Яа-яёЇїІіЄєA-Za-z]+)?)?)',
            r'додай\s+(?:нового\s+)?ліда[.,]?\s*([А-Яа-яёЇїІіЄєA-Za-z]+(?:\s+[А-Яа-яёЇїІіЄєA-Za-z]+(?:\s+[А-Яа-яёЇїІіЄєA-Za-z]+)?)?)',
            r'([А-Я][а-яёЇїІіЄє]+(?:\s+[А-Я][а-яёЇїІіЄє]+)(?:\s+[А-Я][а-яёЇїІіЄє]+)?)',
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if len(name) > 2 and not any(kw in name.lower() for kw in ['додай', 'ліда', 'номер', 'тел', 'email']):
                    result["name"] = name
                    break
        
        # Extract phone
        phone_patterns = [r'\+?380\d{9}', r'\+?\d{10,12}', r'\d{3}[-.\s]?\d{2}[-.\s]?\d{2}[-.\s]?\d{2}']
        for pattern in phone_patterns:
            match = re.search(pattern, text)
            if match:
                result["phone"] = match.group()
                break
        
        # Extract email
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        if email_match:
            result["email"] = email_match.group()
        
        # Extract source
        if "сканер" in text_lower or "scanner" in text_lower:
            result["source"] = "SCANNER"
        elif "партнер" in text_lower or "partner" in text_lower:
            result["source"] = "PARTNER"
        
        # Extract domain
        if "перший" in text_lower or "first" in text_lower:
            result["domain"] = "FIRST"
        elif "другий" in text_lower or "second" in text_lower:
            result["domain"] = "SECOND"
        elif "третій" in text_lower or "third" in text_lower:
            result["domain"] = "THIRD"
        
        return result
    
    # ==================== AI QUERY PROCESSING ====================
    
    async def process_query(self, query: str, leads: list) -> str:
        """Process natural language query about leads using AI."""
        if not self.openai_api_key:
            return self._simple_query_response(query, leads)
        
        try:
            context = self._prepare_context(leads)
            system_prompt = self._build_prompt()
            user_prompt = f"Query: {query}\n\nLeads Data:\n{context}"
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "max_tokens": 500,
                        "temperature": 0.3
                    },
                    timeout=30.0
                )
            
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            else:
                return self._simple_query_response(query, leads)
                
        except Exception as e:
            logger.error(f"AI query error: {e}")
            return self._simple_query_response(query, leads)
    
    def _simple_query_response(self, query: str, leads: list) -> str:
        """Simple rule-based response when AI is not available."""
        query_lower = query.lower()
        
        # Hot leads
        if "гаряч" in query_lower or "hot" in query_lower or "best" in query_lower:
            hot_leads = [l for l in leads if l.get("ai_score", 0) >= 0.6]
            if hot_leads:
                response = "🔥 <b>Гарячі ліди:</b>\n\n"
                for lead in hot_leads[:5]:
                    response += f"• #{lead.get('id')}: {lead.get('full_name')} (score: {lead.get('ai_score', 0):.0%})\n"
                return response
            return "Гарячі ліди не знайдені."
        
        # Count by source
        if "сканер" in query_lower or "scanner" in query_lower:
            count = len([l for l in leads if l.get("source") == "SCANNER"])
            return f"Лідів зі сканера: <b>{count}</b>"
        
        if "партнер" in query_lower or "partner" in query_lower:
            count = len([l for l in leads if l.get("source") == "PARTNER"])
            return f"Лідів від партнерів: <b>{count}</b>"
        
        # Stage counts
        for stage in ["new", "contacted", "qualified", "transferred", "lost"]:
            if stage in query_lower:
                count = len([l for l in leads if l.get("stage", "").lower() == stage.upper()])
                return f"Лідів в стадії {stage}: <b>{count}</b>"
        
        # Default
        return f"Знайдено <b>{len(leads)}</b> лідів. Уточніть ваш запит."
    
    def _prepare_context(self, leads: list) -> str:
        if not leads:
            return "No leads in database."
        
        sample = leads[:30]
        summaries = []
        for lead in sample:
            s = f"ID:{lead.get('id')} | {lead.get('full_name', 'N/A')} | {lead.get('source')} | {lead.get('stage')} | {lead.get('business_domain', '-')}"
            if lead.get('ai_score'):
                s += f" | Score:{lead.get('ai_score', 0):.0%}"
            summaries.append(s)
        return "\n".join(summaries)
    
    def _build_prompt(self) -> str:
        return """Ти — CRM-асистент для системи управління лідрами.

Доступні дані: id, full_name, source (SCANNER/PARTNER/MANUAL), stage (NEW/CONTACTED/QUALIFIED/TRANSFERRED/LOST), business_domain (FIRST/SECOND/THIRD), ai_score (0.0-1.0).

ВІДПОВІДАЙ УКРАЇНСЬКОЮ!
Будь коротким і корисним.
Використовуй форматування HTML (<b>, <i>, •)."""
    
    # ==================== NOTE CATEGORIZATION ====================
    
    async def categorize_note(self, note_content: str) -> str:
        """Categorize a note."""
        if not self.openai_api_key:
            return self._simple_categorize(note_content)
        
        try:
            prompt = f"""Визнач категорію нотатки одним словом: contact, email, meeting, general, problem або success.

Текст: {note_content[:200]}"""
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.openai_api_key}"},
                    json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "max_tokens": 20},
                    timeout=10.0
                )
            
            if response.status_code == 200:
                cat = response.json()["choices"][0]["message"]["content"].strip().lower()
                valid = ["contact", "email", "meeting", "general", "problem", "success"]
                return cat if cat in valid else "general"
        except:
            pass
        
        return self._simple_categorize(note_content)
    
    def _simple_categorize(self, text: str) -> str:
        text_lower = text.lower()
        keywords = {
            "problem": ["проблем", "біль", "скарг", "погано", "issue"],
            "success": ["успіх", "відмінно", "добре", "виграш", "угод"],
            "contact": ["дзвін", "телефон", "розмов", "call"],
            "email": ["email", "лист", "пошта"],
            "meeting": ["зустріч", "мітинг", "нарада"]
        }
        for cat, kws in keywords.items():
            if any(k in text_lower for k in kws):
                return cat
        return "general"


# Singleton
unified_ai = UnifiedAIService()
