# Finance Assistant

Trợ lý tài chính cá nhân chạy trên Mac Mini M4, giao tiếp qua Telegram Bot thông qua OpenClaw.

## Stack

| Layer | Công nghệ |
|---|---|
| Agent runtime | OpenClaw (Node.js) |
| Interface | Telegram Bot |
| LLM | DeepSeek (primary) + Claude (OCR) |
| Backend | FastAPI (Python 3.11+) |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |

## Cài đặt

### 1. Clone & setup env

```bash
cp .env.example .env
# Điền credentials vào .env
```

### 2. Khởi động database

```bash
docker compose up -d
```

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

## Cấu trúc dự án

```
├── backend/              # FastAPI application
│   ├── models/           # SQLAlchemy ORM models
│   ├── schemas/          # Pydantic request/response schemas
│   ├── routers/          # API endpoints
│   ├── services/         # Business logic
│   ├── jobs/             # Scheduled tasks (APScheduler)
│   └── utils/            # Helpers
├── openclaw-skills/      # OpenClaw Skills (thin API wrappers)
├── docker-compose.yml    # PostgreSQL + Redis
└── CLAUDE.md             # System design document
```

## API

Base URL: `http://localhost:8000/api/v1`

| Endpoint | Mô tả |
|---|---|
| `POST /expenses` | Tạo expense |
| `GET /expenses` | List expenses |
| `POST /goals` | Tạo goal |
| `GET /reports/monthly` | Báo cáo tháng |
| `POST /ingestion/ocr` | OCR hóa đơn |
| `GET /market/snapshot` | Thị trường hôm nay |
| `POST /market/advice` | Gợi ý đầu tư |

Chi tiết API: xem Swagger UI tại `http://localhost:8000/docs`
