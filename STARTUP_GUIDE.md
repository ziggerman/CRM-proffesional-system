# 🚀 STARTUP GUIDE - CRM Lead Management System

## Quick Start

### Option 1: Docker Compose (Recommended)
```bash
docker-compose up -d
```

This will start:
- PostgreSQL (port 5432)
- Redis (port 6379)
- API Server (port 8000)
- Celery Worker
- Celery Beat

### Option 2: Local Development

#### 1. Start Redis
```bash
# Install Redis if needed
brew install redis  # macOS
# or
sudo apt install redis-server  # Ubuntu

# Start Redis
redis-server
```

#### 2. Start API Server
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

#### 3. Start Telegram Bot (in new terminal)
```bash
python run_bot.py
```

---

## Environment Variables (.env)

### Required
```
# Database
DATABASE_URL=sqlite+aiosqlite:///./crm.db

# Telegram
TELEGRAM_BOT_TOKEN=8558216907:AAF7jm-fl7OhLt0oZjYYzUY6cdV3Xptqw2c
TELEGRAM_ADMIN_IDS=[123456789,585761464]

# OpenAI (for AI features)
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o-mini
```

### Optional (for Voice Recognition)
```
# HuggingFace - FREE voice transcription
HUGGINGFACE_TOKEN=hf_...
```

---

## Testing Checklist

After starting, verify:

- [ ] Bot responds to /start
- [ ] Main menu displays correctly
- [ ] Can create a new lead
- [ ] Can view leads list
- [ ] Can edit lead stage
- [ ] AI Assistant works (/ai or 🤖 button)
- [ ] Voice mode works (🎤 Voice button)
  - [ ] Voice messages are transcribed
  - [ ] Text commands work in voice mode
- [ ] Sales pipeline accessible
- [ ] Statistics show correctly

---

## Voice Chat Features 🎤

When Voice mode is active, users can:

| Command | Action |
|---------|--------|
| "додай ліда" | Create new lead |
| "покажи ліди" | Show leads list |
| "статистика" | Show statistics |
| "знайди [name]" | Search for lead |
| Voice message | Transcribe & process |

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| GET /api/v1/leads | List leads |
| POST /api/v1/leads | Create lead |
| GET /api/v1/leads/{id} | Get lead details |
| PATCH /api/v1/leads/{id}/stage | Update stage |
| GET /api/v1/dashboard | Dashboard stats |
| POST /api/v1/leads/{id}/analyze | AI analyze |

---

## Troubleshooting

### Bot not responding?
1. Check bot token is correct in .env
2. Verify API server is running on port 8000
3. Check bot.log for errors

### Voice not working?
1. Make sure you're in Voice mode (press 🎤 Voice button)
2. Add HUGGINGFACE_TOKEN to .env for free transcription
3. Or ensure OPENAI_API_KEY is set for paid Whisper

### Database errors?
1. Run migrations: `alembic upgrade head`
2. Or recreate: delete crm.db and restart

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│  Telegram Bot   │────▶│   API Server    │
│  (run_bot.py)  │     │  (FastAPI)      │
└─────────────────┘     └────────┬────────┘
                                  │
                         ┌────────┴────────┐
                         │                 │
                    ┌────▼────┐     ┌────▼────┐
                    │   AI    │     │  Database│
                    │ Service │     │ (SQLite) │
                    └─────────┘     └──────────┘
```

---

## Default Admin ID

Your Telegram ID for admin access: `585761464`
