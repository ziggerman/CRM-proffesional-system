# CRM Lead Management Service

## Архітектура системи

```
crm_bot/
├── app/
│   ├── api/v1/              # HTTP endpoints (FastAPI routers)
│   │   ├── leads.py         # CRUD + stage transitions
│   │   └── sales.py         # Sales pipeline
│   ├── core/                # Config, DB, dependencies
│   │   ├── config.py
│   │   ├── database.py
│   │   └── deps.py
│   ├── models/              # SQLAlchemy ORM models
│   │   ├── lead.py
│   │   └── sale.py
│   ├── schemas/             # Pydantic request/response schemas
│   │   ├── lead.py
│   │   └── sale.py
│   ├── repositories/        # Data access layer
│   │   ├── lead_repo.py
│   │   └── sale_repo.py
│   ├── services/            # Business logic
│   │   ├── lead_service.py
│   │   └── transfer_service.py
│   └── ai/                  # AI integration (isolated)
│       ├── ai_service.py
│       └── prompts.py
├── alembic/                 # DB migrations
├── tests/
├── docker-compose.yml
├── .env.example
└── main.py
```

---

## Як працює система

### Lifecycle лідa

```
[Створення] → new → contacted → qualified → transferred ──→ [Sales: new → kyc → agreement → paid]
                                               ↓
                                             lost
```

1. **Менеджер створює ліда** через `POST /api/v1/leads` (вказує джерело та домен).
2. **Система зберігає ліда** у PostgreSQL зі статусом `new`.
3. **Менеджер просуває ліда** через `PATCH /api/v1/leads/{id}/stage`.
4. **AI-аналіз** запускається через `POST /api/v1/leads/{id}/analyze` — повертає score + recommendation.
5. **Transfer** — `POST /api/v1/leads/{id}/transfer` — доступний тільки при score ≥ 0.6 і наявності домену.

---

## Де використовується AI і чому

AI — це **advisory-шар**, не decision-maker. Він надає рекомендацію, але фінальне рішення залишається за менеджером.

### Що отримує AI

```json
{
  "source": "partner",
  "stage": "qualified",
  "message_count": 12,
  "has_business_domain": true,
  "business_domain": "fintech",
  "days_since_created": 5
}
```

### Що повертає AI

```json
{
  "score": 0.78,
  "recommendation": "transfer_to_sales",
  "reason": "High activity, clear domain, partner source — strong signals"
}
```

### Чому саме ці дані

- **source** — партнерські ліди статистично тепліші
- **stage** — `qualified` сигналізує про підтверджену потребу
- **message_count** — проксі активності та зацікавленості
- **has_business_domain** — без домену sales не зможуть кваліфікувати
- **days_since_created** — довго "зависший" лід знижує ймовірність

---

## Де AI обмежений (Hard Gates)

| Умова | Перевірка | Де |
|-------|-----------|-----|
| score ≥ 0.6 | бізнес-логіка, не AI | `transfer_service.py` |
| наявність домену | бізнес-логіка | `transfer_service.py` |
| коректна послідовність етапів | бізнес-логіка | `lead_service.py` |
| transferred/paid незмінні | бізнес-логіка | `lead_service.py` |

AI **ніколи не змінює стан сам**. Він лише рекомендує.

---

## Які рішення приймає людина

- Просувати ліда по етапах (contacted, qualified)
- Запускати AI-аналіз (коли вважає за потрібне)
- Ігнорувати чи прийняти рекомендацію AI
- Фінально ініціювати transfer

---

## Що б ускладнив у реальному проекті

1. **AI Feedback Loop** — зберігати результати угод та дотренувати модель на реальних даних
2. **Webhooks / Events** — EventBus для нотифікацій менеджера при зміні score
3. **Audit Log** — повнаhistoryзмін стану лідa
4. **Rate limiting AI** — кешувати AI-оцінку (TTL 1 год), не кликати LLM при кожному запиті
5. **Multi-tenant** — ізоляція по компаніях (Row Level Security у PostgreSQL)
6. **Real Telegram integration** — aiogram 3.x + FSM для cold outreach
7. **Background tasks** — авто-запуск AI після N повідомлень (Celery / arq)
8. **Observability** — OpenTelemetry traces для AI latency, Prometheus метрики

---

## Запуск

```bash
cp .env.example .env
docker-compose up -d
alembic upgrade head
uvicorn main:app --reload
```

API документація: http://localhost:8000/docs
