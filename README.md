# Personal CFO Assistant

> AI-powered personal finance assistant for Vietnamese mass affluent users.
> Not just expense tracking — full wealth management, daily net worth briefing, and investment intelligence.

**Chạy trên:** Mac Mini M4, giao tiếp qua Telegram Bot thông qua OpenClaw.

---

## 🎯 Current Status

<!-- BEGIN: phase-status:current-line -->
✅ **Phase 3.6: Menu UX Revamp** (done) — [detail](docs/current/phase-3.6-detailed.md)
<!-- END: phase-status:current-line -->

<!-- BEGIN: phase-status:status-list -->
- ✅ Phase 1: UX Foundation
- ✅ Phase 2: Personality & Care
- ✅ Phase 3A: Wealth Foundation
- ✅ Phase 3.5: Intent Understanding Layer
- ✅ Phase 3.6: Menu UX Revamp ← **just shipped**
- 📋 Phase 3B: Market Intelligence
- 🔮 Phase 4: Investment Intelligence
- 🔮 Phase 5: Behavioral Engine
- 🔮 Phase 6: Scale & Commercialize
<!-- END: phase-status:status-list -->


→ See [`docs/README.md`](docs/README.md) for full roadmap and phase details.

> **Note:** Phase status is auto-synced from
> [`docs/current/phase-status.yaml`](docs/current/phase-status.yaml).
> Edit that file to update the roadmap; the GitHub Action
> `sync-phase-status.yml` rewrites this section on push.

---

## Stack

| Layer | Công nghệ |
|---|---|
| Agent runtime | OpenClaw (Node.js) |
| Interface | Telegram Bot + Mini App |
| Primary LLM | DeepSeek (categorize, storytelling, advice) |
| Vision LLM | Claude API (OCR receipts) |
| Speech-to-Text | OpenAI Whisper (voice storytelling) |
| Backend | FastAPI (Python 3.11+) |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| Dashboard | Notion (read-only sync) |
| Market data | vnstock (stocks), CoinGecko (crypto), cafef (funds), SJC (gold) |

---

## Cài đặt

### 1. Clone & setup env

```bash
cp .env.example .env
# Điền credentials vào .env
```

Required env vars (xem `.env.example` cho đầy đủ):
- `DEEPSEEK_API_KEY` — primary LLM
- `ANTHROPIC_API_KEY` — Vision (OCR)
- `OPENAI_API_KEY` — Whisper (voice)
- `TELEGRAM_BOT_TOKEN` — bot token
- `DATABASE_URL`, `REDIS_URL` — data layer
- `NOTION_API_KEY` + 6 database IDs — dashboard sync

### 2. Khởi động infrastructure

```bash
docker compose up -d
```

Starts PostgreSQL + Redis. Verify: `docker ps`.

### 3. Cài dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 4. Chạy migrations

```bash
alembic upgrade head
```

### 5. Chạy server

```bash
uvicorn backend.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 6. Chạy scheduler (process riêng)

Các scheduled jobs chạy ở process riêng để tránh duplicate khi có nhiều uvicorn worker:

```bash
python -m backend.scheduler
```

**Jobs:**
- `morning_briefing` — 7h sáng (adaptive timing per user)
- `daily_snapshot` — 23:59 mỗi ngày (snapshot asset values)
- `market_poller` — 8h sáng (market snapshot)
- `monthly_report` — 9h sáng ngày 1 mỗi tháng
- `check_milestones` — 8h sáng daily
- `check_empathy_triggers` — mỗi giờ, 7h-22h
- `weekly_fun_facts` — Chủ nhật 19h
- `seasonal_notifier` — 8h sáng (check lunar calendar cho Tết, Trung thu...)

Chỉ chạy **một** instance scheduler. Phase 1 sẽ thay bằng Celery worker.

---

## Cấu trúc dự án

```
├── backend/              # FastAPI application
│   ├── models/           # SQLAlchemy ORM
│   ├── schemas/          # Pydantic request/response
│   ├── routers/          # API endpoints
│   ├── services/         # Business logic
│   │   ├── wealth/       # Asset management + net worth
│   │   ├── capture/      # Storytelling, OCR, voice
│   │   └── briefing_service.py
│   ├── adapters/         # Transport (Telegram, LLM APIs)
│   ├── ports/            # Interfaces for DI/test
│   ├── jobs/             # Scheduled tasks (APScheduler)
│   ├── miniapp/          # Telegram Mini App (Wealth dashboard)
│   └── utils/            # Helpers
│
├── content/              # User-facing content (YAML)
│   ├── asset_categories.yaml
│   ├── briefing_templates.yaml
│   ├── milestone_messages.yaml
│   └── ...
│
├── alembic/              # Database migrations
│
├── openclaw-skills/      # OpenClaw Skills (thin API wrappers)
│
├── docs/                 # Product & technical docs
│   ├── README.md         # Navigation hub
│   ├── current/          # Active docs
│   └── archive/          # Historical (V1 Finance Assistant)
│
├── docker-compose.yml    # PostgreSQL + Redis
├── CLAUDE.md             # Master technical spec
└── README.md             # You are here
```

---

## API Endpoints

Base URL: `http://localhost:8000/api/v1`

### Wealth (core của V2)
| Endpoint | Mô tả |
|---|---|
| `GET /wealth/overview` | Net worth + breakdown + change |
| `GET /wealth/trend?days=30\|90\|365` | Historical net worth |
| `GET /wealth/level` | Wealth level + next milestone |

### Assets
| Endpoint | Mô tả |
|---|---|
| `POST /assets` | Thêm asset mới |
| `GET /assets` | List assets |
| `PUT /assets/{id}/value` | Update giá trị hiện tại |
| `DELETE /assets/{id}` | Soft delete (mark sold) |

### Transactions
| Endpoint | Mô tả |
|---|---|
| `POST /transactions` | Manual transaction |
| `GET /transactions` | List (filter: month, category) |
| `POST /storytelling/extract` | AI extract từ câu chuyện |
| `POST /storytelling/confirm` | Save extracted transactions |

### Ingestion
| Endpoint | Mô tả |
|---|---|
| `POST /ingestion/ocr` | Upload ảnh hóa đơn |
| `POST /ingestion/voice` | Upload voice message |

### Other
| Endpoint | Mô tả |
|---|---|
| `GET /reports/monthly` | Báo cáo tháng |
| `GET /market/snapshot` | Thị trường hôm nay |
| `POST /market/advice` | Gợi ý đầu tư |
| `POST /goals` | Tạo financial goal |

**Full API docs:** Swagger UI tại `http://localhost:8000/docs`

---

## Documentation

- 🎯 **[Product Strategy](docs/current/strategy.md)** — Vision, positioning, roadmap
- 🔧 **[Technical Spec (CLAUDE.md)](CLAUDE.md)** — Full system design, đọc trước khi code
- 📋 **[Current Phase (3A)](docs/current/phase-3a-detailed.md)** — Implementation guide
- 📚 **[All docs](docs/README.md)** — Navigation hub
- 📝 **[Migration Notes V1→V2](docs/archive/MIGRATION_NOTES.md)** — Context về pivot

---

## Development

### Testing
```bash
cd backend
pytest
```

### Linting
```bash
# Python
ruff check backend/
ruff format backend/
```

### Alembic — Create new migration
```bash
alembic revision --autogenerate -m "add assets table"
alembic upgrade head
```

---

## History

This project pivoted from **"Finance Assistant"** (V1, expense tracking focus) to **"Personal CFO"** (V2, wealth management focus) in April 2026. For pivot context and V1 archived docs, see [`docs/archive/`](docs/archive/).
