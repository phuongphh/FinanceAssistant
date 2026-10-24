# Phase 4.2.5: Admin Observability — User Stories & Issues

> **Companion document**: `phase-4.2.5-detailed.md`
> **Total**: 23 stories across 7 Epics
> **Estimated**: ~65 story points (~3 sprints)
> **Convention**: Epic-as-parent, Story-as-child (numbered Epics theo Phase 4.2+ convention)
> **Last updated**: 2026-05-13 (v2.0)

---

## What's new in v2.0 (2026-05-13)

- ✅ **Renamed Phase 3.6 → Phase 4.2.5** để align với master-roadmap (3.6 đã được Menu UX Revamp dùng và shipped 2026-05-05).
- ✅ **Removed Story 1.5 (bridge migration)** vì Phase 3.5 đã ship 2026-05-02 — cột `messages.resolved_by` đã tồn tại. Total stories: 24 → 23.
- ✅ Labels updated: `phase-3.6` → `phase-4.2.5`.
- ✅ Story 2.4 dependency simplified: chỉ cần `1.3`, không cần bridge migration nữa.
- ✅ Position note: chèn giữa Phase 4.2 (✅ done) và Phase 5.0 (Encryption End-to-End).

### What's new in v1.1 (2026-05-13, historical)

- ✅ Added **Implementation Skeleton** section cho mọi backend story (Epic 1, 2, 3, 6, 7).
- ✅ Story 1.1 update: seed credentials cụ thể + `force_password_change=true` flag.
- ✅ Story 2.4 update: tier thresholds chính thức (100M / 500M / 5B VND).

---

## Conventions

### Labels
- `backend`, `frontend`, `infra`, `security`, `db`, `auth`
- `epic`, `story`, `task`
- `phase-4.2.5`, `admin-console`
- Size: `XS` (≤2h), `S` (½ day), `M` (1 day), `L` (2 days), `XL` (3+ days)

### Sprint planning

| Sprint | Focus | Epics |
|--------|-------|-------|
| Sprint 1 (tuần 1) | Backend foundation + Core APIs phần 1 | Epic 1 (full), Epic 2 (2.1–2.3) |
| Sprint 2 (tuần 2) | Remaining APIs + Frontend foundation | Epic 2 (2.4–2.5), Epic 3, Epic 4 |
| Sprint 3 (tuần 3) | UI components + Security + Deploy | Epic 5, Epic 6, Epic 7 |

---

## Epic 1: Backend Foundation & Auth

**Goal**: Đặt nền móng cho admin console — data model, authentication, audit log.

**Stories**: 4 · **Size**: ~11 SP

---

### Story 1.1: Admin user data model & migration + seed

**Type**: Story · **Size**: M · **Labels**: backend, db, auth
**Depends on**: —
**Sprint**: 1

**User story**:
As a developer, I want a dedicated `admin_users` table separate from `users` table so that admin authentication is decoupled from end-user (Telegram) authentication, with secure initial seed credentials.

**Acceptance Criteria**:
- [ ] Migration tạo bảng `admin_users` với schema theo Section 8.1 của detailed doc.
- [ ] Cột `force_password_change BOOLEAN DEFAULT TRUE` — flag bắt buộc đổi password ở lần login đầu.
- [ ] Indexes trên `email` (unique).
- [ ] Migration script reversible (có `downgrade`).
- [ ] Seed script tạo 1 admin: email `phuongphh@nuitruc.ai`, password `admin` (đọc từ env), `force_password_change=True`.
- [ ] Pydantic schema `AdminUserOut` KHÔNG bao giờ expose `password_hash`.

**Technical Notes**:
- Password hash bằng `bcrypt`, cost factor 12.
- Seed script idempotent.
- Xóa env var `INITIAL_ADMIN_PASSWORD` khỏi `.env` sau khi seed.

**Implementation Skeleton**:

📁 Files: `migrations/versions/XXXX_create_admin_users.py`, `app/models/admin_user.py`, `app/schemas/admin.py`, `scripts/seed_admin.py`

```python
# app/models/admin_user.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(String(50), nullable=False, default="super_admin")
    tenant_id = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    force_password_change = Column(Boolean, default=True, nullable=False)
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())
```

```python
# app/schemas/admin.py
from datetime import datetime
from pydantic import BaseModel, EmailStr

class AdminUserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str | None
    role: str
    is_active: bool
    force_password_change: bool
    last_login_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    force_password_change: bool
    admin: AdminUserOut

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str  # validate min 12 chars, có chữ + số
```

```python
# scripts/seed_admin.py
import os
import bcrypt
from app.db.session import SessionLocal
from app.models.admin_user import AdminUser

def seed():
    db = SessionLocal()
    email = os.getenv("INITIAL_ADMIN_EMAIL", "phuongphh@nuitruc.ai")
    pwd = os.getenv("INITIAL_ADMIN_PASSWORD", "admin")

    if db.query(AdminUser).filter_by(email=email).first():
        print(f"✓ Admin {email} already exists, skip seed")
        return

    hashed = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt(rounds=12))
    admin = AdminUser(
        email=email,
        password_hash=hashed.decode(),
        full_name="Phuong",
        role="super_admin",
        force_password_change=True,
    )
    db.add(admin)
    db.commit()
    print(f"✓ Seeded admin: {email} (must change password on first login)")

if __name__ == "__main__":
    seed()
```

**Test scenarios**:
- TC1: Migration apply trên DB clean → bảng tồn tại với đủ columns.
- TC2: Migration rollback không lỗi.
- TC3: Run seed lần 1 → tạo admin với `force_password_change=True`.
- TC4: Run seed lần 2 → in "already exists", không duplicate.
- TC5: Query `AdminUserOut` không trả `password_hash`.

---

### Story 1.2: Login endpoint + force password change flow

**Type**: Story · **Size**: L · **Labels**: backend, api, auth, security
**Depends on**: 1.1
**Sprint**: 1

**User story**:
As an admin, I want to login với email/password and receive a JWT token, with a forced password change flow on first login so that the weak initial password "admin" is replaced immediately.

**Acceptance Criteria**:
- [ ] `POST /api/admin/auth/login` accept email + password.
- [ ] JWT (HS256, expiry 1h) chứa: `admin_id`, `email`, `role`, `restricted`, `jti`, `iat`, `exp`.
- [ ] Response: `access_token`, `expires_in`, `force_password_change`, `admin`.
- [ ] Update `last_login_at`.
- [ ] Rate limit: 5 attempts / 15 phút / IP → 429.
- [ ] Invalid credentials → 401 message generic.
- [ ] Inactive admin → 403.
- [ ] `POST /api/admin/auth/change-password` đổi password, set `force_password_change=False`.
- [ ] Validator new password: min 12 chars, có chữ + số.
- [ ] Khi `force_password_change=True`, JWT có `restricted=True`, chỉ cho phép `/auth/change-password` + `/auth/me`.

**Implementation Skeleton**:

📁 Files: `app/api/admin/auth.py`, `app/services/admin_auth.py`, `app/utils/jwt_utils.py`

```python
# app/utils/jwt_utils.py
import os, secrets
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError

SECRET = os.environ["ADMIN_JWT_SECRET"]
ALGORITHM = "HS256"
EXPIRY_MINUTES = int(os.getenv("ADMIN_JWT_EXPIRY_MINUTES", 60))

def create_token(admin_id: int, email: str, role: str,
                 restricted: bool = False) -> tuple[str, str, int]:
    """Returns (token, jti, expires_in_seconds)."""
    jti = secrets.token_hex(16)
    exp = datetime.now(timezone.utc) + timedelta(minutes=EXPIRY_MINUTES)
    payload = {
        "admin_id": admin_id, "email": email, "role": role,
        "restricted": restricted, "jti": jti,
        "iat": datetime.now(timezone.utc), "exp": exp,
    }
    return jwt.encode(payload, SECRET, ALGORITHM), jti, EXPIRY_MINUTES * 60

def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
```

```python
# app/services/admin_auth.py
import redis, os

r = redis.from_url(os.getenv("ADMIN_RATE_LIMIT_REDIS_URL", "redis://localhost:6379/1"))
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 900  # 15 phút

def check_rate_limit(ip: str) -> bool:
    return int(r.get(f"admin:login_attempts:{ip}") or 0) < RATE_LIMIT_MAX

def record_attempt(ip: str):
    key = f"admin:login_attempts:{ip}"
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, RATE_LIMIT_WINDOW)
    pipe.execute()
```

```python
# app/api/admin/auth.py
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.admin import LoginRequest, LoginResponse, ChangePasswordRequest
from app.utils.jwt_utils import create_token
from app.services.admin_auth import check_rate_limit, record_attempt
from app.services.admin_audit import log_action

router = APIRouter(prefix="/auth", tags=["admin-auth"])

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host
    if not check_rate_limit(ip):
        raise HTTPException(429, "Too many login attempts")

    admin = db.query(AdminUser).filter_by(email=body.email).first()
    valid = admin and bcrypt.checkpw(body.password.encode(),
                                     admin.password_hash.encode())
    if not valid:
        record_attempt(ip)
        log_action(db, None, "login_failed",
                  payload={"email": body.email}, request=request)
        raise HTTPException(401, "Invalid credentials")
    if not admin.is_active:
        raise HTTPException(403, "Account disabled")

    admin.last_login_at = func.now()
    db.commit()
    db.refresh(admin)
    token, _, exp = create_token(admin.id, admin.email, admin.role,
                                  restricted=admin.force_password_change)
    log_action(db, admin.id, "login_success", request=request)
    return LoginResponse(
        access_token=token, expires_in=exp,
        force_password_change=admin.force_password_change, admin=admin,
    )

# /change-password endpoint sẽ inject get_current_admin_any từ Story 1.3
```

**Test scenarios**:
- TC1: Valid creds → 200 + token + `force_password_change=True` ở first login.
- TC2: Wrong password → 401, audit log có `login_failed`.
- TC3: 6 lần thử sai → request 6 trả 429.
- TC4: Restricted token gọi `/stats/overview` → 403.
- TC5: Change password thành công → `force_password_change=False`.
- TC6: Password mới yếu → 400.

---

### Story 1.3: Auth dependency + logout endpoint

**Type**: Story · **Size**: M · **Labels**: backend, api, auth
**Depends on**: 1.2
**Sprint**: 1

**User story**:
As a developer, I want a reusable FastAPI dependency `get_current_admin()` so that mọi admin endpoint dễ dàng require authentication.

**Acceptance Criteria**:
- [ ] `app/api/admin/deps.py` có 2 dependency:
  - `get_current_admin()`: reject nếu `restricted=True`.
  - `get_current_admin_any()`: bypass restricted (cho `/auth/change-password`, `/auth/me`).
- [ ] Decode JWT → 401 nếu invalid/expired.
- [ ] Check Redis blacklist trước khi accept.
- [ ] `GET /auth/me` trả admin info.
- [ ] `POST /auth/logout` add `jti` vào blacklist với TTL = remaining lifetime.

**Implementation Skeleton**:

```python
# app/api/admin/deps.py
import redis, os, time
from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session
from jose import JWTError
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.utils.jwt_utils import decode_token

r = redis.from_url(os.getenv("ADMIN_RATE_LIMIT_REDIS_URL", "redis://localhost:6379/1"))

def _resolve_admin(authorization: str, db: Session, allow_restricted: bool):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(401, "Invalid token")

    if r.exists(f"admin:token_blacklist:{payload['jti']}"):
        raise HTTPException(401, "Token revoked")

    admin = db.query(AdminUser).get(payload["admin_id"])
    if not admin or not admin.is_active:
        raise HTTPException(403, "Inactive")

    if payload.get("restricted") and not allow_restricted:
        raise HTTPException(403, "Must change password first")

    return admin

def get_current_admin(authorization: str = Header(None),
                     db: Session = Depends(get_db)) -> AdminUser:
    return _resolve_admin(authorization, db, allow_restricted=False)

def get_current_admin_any(authorization: str = Header(None),
                         db: Session = Depends(get_db)) -> AdminUser:
    return _resolve_admin(authorization, db, allow_restricted=True)
```

```python
# Thêm vào app/api/admin/auth.py:
from app.api.admin.deps import get_current_admin_any
from app.schemas.admin import AdminUserOut

@router.get("/me", response_model=AdminUserOut)
async def me(admin: AdminUser = Depends(get_current_admin_any)):
    return admin

@router.post("/logout")
async def logout(
    request: Request,
    authorization: str = Header(None),
    admin: AdminUser = Depends(get_current_admin_any),
    db: Session = Depends(get_db),
):
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    exp_ts = payload["exp"].timestamp() if hasattr(payload["exp"], "timestamp") \
             else payload["exp"]
    ttl = max(0, int(exp_ts - time.time()))
    r.setex(f"admin:token_blacklist:{payload['jti']}", ttl, "1")
    log_action(db, admin.id, "logout", request=request)
    return {"message": "Logged out"}
```

**Test scenarios**:
- TC1: Valid token → endpoint chạy bình thường.
- TC2: Logout xong → token bị reject 401.
- TC3: Token tampered → 401.
- TC4: Restricted token gọi `/me` OK, gọi `/stats/overview` → 403.

---

### Story 1.4: Audit log infrastructure

**Type**: Story · **Size**: M · **Labels**: backend, db, security
**Depends on**: 1.1
**Sprint**: 1

**User story**:
As a security-conscious developer, I want every admin action logged to `admin_audit_log` so that we have full traceability.

**Acceptance Criteria**:
- [ ] Migration tạo bảng `admin_audit_log`.
- [ ] Service `app/services/admin_audit.py` với `log_action(...)`.
- [ ] IP & user agent extract từ Request.
- [ ] `GET /api/admin/audit?limit=50&offset=0` paginated, filter optional.
- [ ] Append-only.

**Implementation Skeleton**:

📁 Files: `app/models/admin_audit_log.py`, `app/services/admin_audit.py`, `app/api/admin/audit.py`

```python
# app/models/admin_audit_log.py
from sqlalchemy import Column, BigInteger, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, INET
from sqlalchemy.sql import func
from app.db.base import Base

class AdminAuditLog(Base):
    __tablename__ = "admin_audit_log"

    id = Column(BigInteger, primary_key=True)
    admin_user_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True)
    action = Column(String(100), nullable=False, index=True)
    target_type = Column(String(50), index=True)
    target_id = Column(String(255), index=True)
    payload = Column(JSONB)
    ip_address = Column(INET)
    user_agent = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
```

```python
# app/services/admin_audit.py
from sqlalchemy.orm import Session
from fastapi import Request
from app.models.admin_audit_log import AdminAuditLog

def log_action(
    db: Session, admin_id: int | None, action: str,
    target_type: str | None = None, target_id: str | None = None,
    payload: dict | None = None, request: Request | None = None,
):
    entry = AdminAuditLog(
        admin_user_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
        ip_address=request.client.host if request else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    db.add(entry)
    db.commit()
```

```python
# app/api/admin/audit.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.admin.deps import get_current_admin
from app.models.admin_user import AdminUser
from app.models.admin_audit_log import AdminAuditLog

router = APIRouter(prefix="/audit", tags=["admin-audit"])

@router.get("")
async def list_audit(
    limit: int = Query(50, le=200), offset: int = 0,
    action: str | None = None, target_type: str | None = None,
    admin: AdminUser = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    q = db.query(AdminAuditLog)
    if action: q = q.filter(AdminAuditLog.action == action)
    if target_type: q = q.filter(AdminAuditLog.target_type == target_type)
    total = q.count()
    entries = q.order_by(AdminAuditLog.created_at.desc())\
                .limit(limit).offset(offset).all()
    return {
        "total": total, "limit": limit, "offset": offset,
        "entries": [
            {
                "id": e.id, "admin_user_id": e.admin_user_id,
                "action": e.action, "target_type": e.target_type,
                "target_id": e.target_id, "payload": e.payload,
                "ip_address": str(e.ip_address) if e.ip_address else None,
                "created_at": e.created_at.isoformat(),
            } for e in entries
        ]
    }
```

**Test scenarios**:
- TC1: Login success → row `action=login_success`.
- TC2: List endpoint sort DESC theo created_at.
- TC3: Filter `action=login_failed` chỉ trả failed entries.

---

### ~~Story 1.5: Bridge migration — Add `messages.resolved_by` column~~ — REMOVED (v2.0)

> ✅ **Obsolete since Phase 3.5 ship (2026-05-02)**. Cột `messages.resolved_by` đã tồn tại với các giá trị `rule` / `llm_classifier` / `clarification` được set bởi intent dispatcher. Phase 4.2.5 chỉ đọc trực tiếp, không cần bridge migration.
>
> **Migration path nếu có row legacy (rows cũ trước Phase 3.5)**: Query trong Story 2.4 đã filter `WHERE resolved_by IS NOT NULL AND resolved_by != 'legacy'` để loại trừ — không cần backfill thêm.

---

## Epic 2: Analytics APIs

**Goal**: Cung cấp toàn bộ data endpoints cho dashboard.

**Stories**: 5 · **Size**: ~14 SP

---

### Story 2.1: Overview stats endpoint

**Type**: Story · **Size**: L · **Labels**: backend, api, db
**Depends on**: 1.3
**Sprint**: 1

**User story**:
As an admin, I want a single endpoint trả về tất cả KPI tổng quan so that hero section load nhanh trong 1 round-trip.

**Acceptance Criteria**:
- [ ] `GET /api/admin/stats/overview?period=30d` (default `30d`, options: `7d`, `14d`, `30d`, `90d`).
- [ ] Response theo Section 7.3 detailed doc.
- [ ] Single CTE query.
- [ ] Delta % so với period trước.
- [ ] Redis cache TTL 5 phút.

**Implementation Skeleton**:

📁 Files: `app/api/admin/stats.py`, `app/services/admin_metrics.py`

```python
# app/services/admin_metrics.py
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.orm import Session
import redis, json, os

r = redis.from_url(os.getenv("ADMIN_RATE_LIMIT_REDIS_URL", "redis://localhost:6379/1"))
CACHE_TTL = 300

PERIOD_DAYS = {"7d": 7, "14d": 14, "30d": 30, "90d": 90}

OVERVIEW_SQL = text("""
WITH
  total_users AS (SELECT COUNT(*) AS c FROM users),
  users_past AS (
    SELECT COUNT(*) AS c FROM users
    WHERE created_at < NOW() - (:days || ' days')::interval
  ),
  new_users_period AS (
    SELECT COUNT(*) AS c FROM users
    WHERE created_at >= NOW() - (:days || ' days')::interval
  ),
  dau AS (
    SELECT COUNT(DISTINCT user_id) AS c FROM messages
    WHERE created_at >= CURRENT_DATE
  ),
  wau AS (
    SELECT COUNT(DISTINCT user_id) AS c FROM messages
    WHERE created_at >= NOW() - INTERVAL '7 days'
  ),
  mau AS (
    SELECT COUNT(DISTINCT user_id) AS c FROM messages
    WHERE created_at >= NOW() - INTERVAL '30 days'
  ),
  llm_cost AS (
    SELECT COALESCE(SUM(cost_usd), 0) AS c FROM llm_calls
    WHERE created_at >= DATE_TRUNC('month', NOW())
  ),
  llm_cost_prev AS (
    SELECT COALESCE(SUM(cost_usd), 0) AS c FROM llm_calls
    WHERE created_at >= DATE_TRUNC('month', NOW()) - INTERVAL '1 month'
      AND created_at < DATE_TRUNC('month', NOW())
  ),
  asset_users AS (
    SELECT COUNT(DISTINCT user_id) AS c FROM assets WHERE deleted_at IS NULL
  ),
  briefing_opens AS (
    SELECT COUNT(DISTINCT user_id) AS c FROM feature_events
    WHERE feature_key = 'morning_briefing'
      AND created_at >= NOW() - INTERVAL '7 days'
  ),
  errors AS (
    SELECT COUNT(*) FILTER (WHERE status = 'error') AS errors,
           COUNT(*) AS total
    FROM messages WHERE created_at >= NOW() - INTERVAL '7 days'
  )
SELECT
  (SELECT c FROM total_users) AS total_users,
  ROUND(((SELECT c FROM total_users) - (SELECT c FROM users_past))::numeric
         / NULLIF((SELECT c FROM users_past), 0) * 100) AS total_users_delta_pct,
  (SELECT c FROM new_users_period) AS new_users_period,
  (SELECT c FROM dau) AS dau,
  (SELECT c FROM wau) AS wau,
  (SELECT c FROM mau) AS mau,
  ROUND((SELECT c FROM dau)::numeric / NULLIF((SELECT c FROM mau), 0) * 100) AS stickiness_pct,
  ROUND((SELECT c FROM llm_cost)::numeric, 2) AS total_llm_cost_usd,
  ROUND(((SELECT c FROM llm_cost) - (SELECT c FROM llm_cost_prev))::numeric
         / NULLIF((SELECT c FROM llm_cost_prev), 0) * 100) AS cost_delta_pct,
  ROUND((SELECT c FROM llm_cost)::numeric / NULLIF((SELECT c FROM wau), 0), 3)
    AS avg_cost_per_active_user,
  ROUND((SELECT c FROM asset_users)::numeric
         / NULLIF((SELECT c FROM total_users), 0) * 100, 1) AS asset_coverage_pct,
  ROUND((SELECT c FROM briefing_opens)::numeric
         / NULLIF((SELECT c FROM wau), 0) * 100, 1) AS briefing_open_rate_pct,
  ROUND((SELECT errors FROM errors)::numeric
         / NULLIF((SELECT total FROM errors), 0) * 100, 1) AS error_rate_pct
""")

def get_overview(db: Session, period: str = "30d") -> dict:
    days = PERIOD_DAYS.get(period, 30)
    cache_key = f"admin:stats:overview:{period}"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)

    row = db.execute(OVERVIEW_SQL, {"days": days}).first()
    result = {
        "period": period,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": dict(row._mapping),
    }
    r.setex(cache_key, CACHE_TTL, json.dumps(result, default=str))
    return result
```

```python
# app/api/admin/stats.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.admin.deps import get_current_admin
from app.services.admin_metrics import get_overview

router = APIRouter(prefix="/stats", tags=["admin-stats"])

@router.get("/overview")
async def overview(
    period: str = Query("30d", regex="^(7d|14d|30d|90d)$"),
    admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    return get_overview(db, period)
```

**Test scenarios**:
- TC1: First call compute + cache. Second call <50ms từ cache.
- TC2: Period `7d` trả khác `30d`.
- TC3: MAU=0 → stickiness=0, không divide-by-zero.

---

### Story 2.2: User growth & DAU chart endpoints

**Type**: Story · **Size**: M · **Labels**: backend, api, db
**Depends on**: 1.3
**Sprint**: 1

**Acceptance Criteria**:
- [ ] `GET /api/admin/charts/user-growth?days=30` → `[{date, cumulative, new_users}]`.
- [ ] `GET /api/admin/charts/dau?days=14` → `[{date, dau}]`.
- [ ] Fill missing dates với 0.
- [ ] Cache Redis 30 phút.

**Implementation Skeleton**:

```python
# app/api/admin/charts.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.admin.deps import get_current_admin
import redis, json, os

r = redis.from_url(os.getenv("ADMIN_RATE_LIMIT_REDIS_URL"))
router = APIRouter(prefix="/charts", tags=["admin-charts"])

USER_GROWTH_SQL = text("""
WITH date_series AS (
  SELECT generate_series(
    (NOW() - (:days || ' days')::interval)::date,
    NOW()::date,
    '1 day'
  )::date AS d
),
daily_new AS (
  SELECT DATE(created_at) AS d, COUNT(*) AS c FROM users
  WHERE created_at >= NOW() - (:days || ' days')::interval
  GROUP BY DATE(created_at)
)
SELECT
  ds.d AS date,
  COALESCE(dn.c, 0) AS new_users,
  (SELECT COUNT(*) FROM users WHERE DATE(created_at) <= ds.d) AS cumulative
FROM date_series ds LEFT JOIN daily_new dn ON dn.d = ds.d
ORDER BY ds.d
""")

DAU_SQL = text("""
WITH date_series AS (
  SELECT generate_series(
    (NOW() - (:days || ' days')::interval)::date,
    NOW()::date,
    '1 day'
  )::date AS d
),
daily AS (
  SELECT DATE(created_at) AS d, COUNT(DISTINCT user_id) AS c FROM messages
  WHERE created_at >= NOW() - (:days || ' days')::interval
  GROUP BY DATE(created_at)
)
SELECT ds.d AS date, COALESCE(daily.c, 0) AS dau
FROM date_series ds LEFT JOIN daily ON daily.d = ds.d
ORDER BY ds.d
""")

def _cached(key: str, ttl: int, builder):
    cached = r.get(key)
    if cached: return json.loads(cached)
    result = builder()
    r.setex(key, ttl, json.dumps(result, default=str))
    return result

@router.get("/user-growth")
async def user_growth(days: int = Query(30, ge=7, le=90),
                     admin = Depends(get_current_admin),
                     db: Session = Depends(get_db)):
    return _cached(f"admin:chart:growth:{days}", 1800, lambda: {
        "data": [dict(row._mapping) for row in
                  db.execute(USER_GROWTH_SQL, {"days": days})]
    })

@router.get("/dau")
async def dau(days: int = Query(14, ge=7, le=90),
             admin = Depends(get_current_admin),
             db: Session = Depends(get_db)):
    return _cached(f"admin:chart:dau:{days}", 1800, lambda: {
        "data": [dict(row._mapping) for row in
                  db.execute(DAU_SQL, {"days": days})]
    })
```

**Test scenarios**:
- TC1: `days=7` → array length = 7 hoặc 8.
- TC2: Ngày không có user mới → `new_users=0`.
- TC3: `cumulative` monotonically non-decreasing.

---

### Story 2.3: Feature events tracking + clicks endpoint

**Type**: Story · **Size**: M · **Labels**: backend, api, db
**Depends on**: 1.3
**Sprint**: 1

**Acceptance Criteria**:
- [ ] Migration tạo bảng `feature_events`.
- [ ] Service `record_feature_event()` fire-and-forget.
- [ ] Tích hợp vào ≥8 bot handler.
- [ ] Catalog `feature_keys` chuẩn hóa.
- [ ] `GET /api/admin/charts/feature-clicks?days=30&limit=10`.

**Implementation Skeleton**:

📁 Files: `app/models/feature_event.py`, `app/services/feature_tracker.py`, `app/constants/feature_keys.py`

```python
# app/constants/feature_keys.py
FEATURE_KEYS = {
    "total_assets":     "Tổng tài sản",
    "morning_briefing": "Briefing sáng",
    "expense_capture":  "Ghi chi tiêu",
    "net_worth_chart":  "Net worth chart",
    "crypto_holding":   "Crypto holding",
    "gold_sjc":         "Vàng SJC",
    "stock_portfolio":  "Cổ phiếu",
    "real_estate":      "Bất động sản",
    "settings":         "Cài đặt",
    "other":            "Khác",
}
```

```python
# app/models/feature_event.py
from sqlalchemy import Column, BigInteger, String, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.db.base import Base

class FeatureEvent(Base):
    __tablename__ = "feature_events"
    id = Column(BigInteger, primary_key=True)
    user_id = Column(String(50), nullable=False, index=True)
    tenant_id = Column(Integer, nullable=False)
    feature_key = Column(String(100), nullable=False, index=True)
    event_metadata = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
```

```python
# app/services/feature_tracker.py
import asyncio
from app.models.feature_event import FeatureEvent
from app.db.session import SessionLocal

async def record_feature_event(user_id: str, tenant_id: int,
                               feature_key: str, metadata: dict | None = None):
    """Fire-and-forget. Không block caller."""
    def _write():
        db = SessionLocal()
        try:
            db.add(FeatureEvent(
                user_id=user_id, tenant_id=tenant_id,
                feature_key=feature_key, event_metadata=metadata,
            ))
            db.commit()
        finally:
            db.close()
    asyncio.get_event_loop().run_in_executor(None, _write)
```

```python
# Trong bot handlers:
from app.services.feature_tracker import record_feature_event

async def handle_morning_briefing(user_id, tenant_id, ...):
    # ... existing logic ...
    await record_feature_event(user_id, tenant_id, "morning_briefing")
```

```python
# Thêm vào app/api/admin/charts.py:
from app.constants.feature_keys import FEATURE_KEYS

FEATURE_CLICKS_SQL = text("""
SELECT feature_key, COUNT(*) AS clicks
FROM feature_events
WHERE created_at >= NOW() - (:days || ' days')::interval
GROUP BY feature_key
ORDER BY clicks DESC
LIMIT :limit
""")

@router.get("/feature-clicks")
async def feature_clicks(
    days: int = Query(30, ge=7, le=90),
    limit: int = Query(10, le=20),
    admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rows = db.execute(FEATURE_CLICKS_SQL, {"days": days, "limit": limit})
    return {
        "data": [
            {
                "feature_key": row.feature_key,
                "feature_name": FEATURE_KEYS.get(row.feature_key, row.feature_key),
                "clicks": row.clicks,
            }
            for row in rows
        ]
    }
```

**Test scenarios**:
- TC1: Trigger feature trong bot → có row trong DB sau ~100ms.
- TC2: Endpoint sort DESC.
- TC3: `feature_name` tiếng Việt đúng.

---

### Story 2.4: Intent breakdown + tier distribution endpoints

**Type**: Story · **Size**: M · **Labels**: backend, api, db
**Depends on**: 1.3 (Phase 3.5 đã ship `resolved_by` column từ 2026-05-02)
**Sprint**: 2

**Acceptance Criteria**:
- [ ] `GET /api/admin/charts/intent-breakdown?days=7` → 3 categories (`legacy` exclude).
- [ ] `GET /api/admin/charts/user-tiers` → 4 tier.
- [ ] **Tier thresholds** (Phuong xác nhận 2026-05-13):
  - `starter`: < 100M VND
  - `young_pro`: 100M – 500M VND
  - `mass_affluent`: 500M – 5B VND
  - `hnw`: ≥ 5B VND
- [ ] Service `tier_classifier.py` reusable.

**Implementation Skeleton**:

📁 Files: `app/services/tier_classifier.py`, thêm endpoints vào `charts.py`

```python
# app/services/tier_classifier.py
from sqlalchemy import text

TIER_THRESHOLDS_VND = {
    "starter": (0, 100_000_000),
    "young_pro": (100_000_000, 500_000_000),
    "mass_affluent": (500_000_000, 5_000_000_000),
    "hnw": (5_000_000_000, float("inf")),
}

TIER_LABELS = {
    "starter": "Starter",
    "young_pro": "Young Pro",
    "mass_affluent": "Mass Affluent",
    "hnw": "HNW",
}

def classify_tier(total_asset_vnd: float) -> str:
    if total_asset_vnd is None: total_asset_vnd = 0
    for tier, (lo, hi) in TIER_THRESHOLDS_VND.items():
        if lo <= total_asset_vnd < hi:
            return tier
    return "hnw"

TIER_DISTRIBUTION_SQL = text("""
WITH user_assets AS (
  SELECT u.user_id,
         COALESCE(SUM(a.current_value_vnd), 0) AS total_value
  FROM users u
  LEFT JOIN assets a ON a.user_id = u.user_id AND a.deleted_at IS NULL
  GROUP BY u.user_id
)
SELECT
  CASE
    WHEN total_value < 100000000 THEN 'starter'
    WHEN total_value < 500000000 THEN 'young_pro'
    WHEN total_value < 5000000000 THEN 'mass_affluent'
    ELSE 'hnw'
  END AS tier,
  COUNT(*) AS count
FROM user_assets
GROUP BY tier
""")
```

```python
# Thêm vào app/api/admin/charts.py:
from app.services.tier_classifier import TIER_LABELS, TIER_DISTRIBUTION_SQL

INTENT_SQL = text("""
SELECT resolved_by, COUNT(*) AS count,
       ROUND((COUNT(*)::numeric * 100 / SUM(COUNT(*)) OVER ())::numeric, 1) AS pct
FROM messages
WHERE created_at >= NOW() - (:days || ' days')::interval
  AND resolved_by IS NOT NULL
  AND resolved_by != 'legacy'
GROUP BY resolved_by
ORDER BY count DESC
""")

INTENT_LABELS = {
    "rule": "Rule-based (zero cost)",
    "llm_classifier": "LLM classified",
    "clarification": "Cần clarify",
}

@router.get("/intent-breakdown")
async def intent_breakdown(
    days: int = Query(7, ge=1, le=30),
    admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rows = db.execute(INTENT_SQL, {"days": days})
    return {
        "data": [
            {
                "resolved_by": row.resolved_by,
                "label": INTENT_LABELS.get(row.resolved_by, row.resolved_by),
                "count": row.count,
                "pct": float(row.pct),
            }
            for row in rows
        ]
    }

@router.get("/user-tiers")
async def user_tiers(
    admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rows = db.execute(TIER_DISTRIBUTION_SQL)
    by_tier = {row.tier: row.count for row in rows}
    return {
        "data": [
            {"tier": t, "label": TIER_LABELS[t], "count": by_tier.get(t, 0)}
            for t in ["starter", "young_pro", "mass_affluent", "hnw"]
        ]
    }
```

**Test scenarios**:
- TC1: Intent sum pct = 100 ± 1%.
- TC2: User asset 50M → `starter`. 200M → `young_pro`. 2B → `mass_affluent`. 8B → `hnw`.
- TC3: Endpoint exclude `legacy`.

---

### Story 2.5: Cohort retention endpoint

**Type**: Story · **Size**: L · **Labels**: backend, api, db
**Depends on**: 1.3
**Sprint**: 2

**Acceptance Criteria**:
- [ ] `GET /api/admin/charts/cohort-retention?weeks=8`.
- [ ] Response theo Section 7.4.
- [ ] Cell `null` nếu chưa đến tuần đó.
- [ ] Cache Redis 24h.
- [ ] Performance <500ms với <100 user.

**Implementation Skeleton**:

```python
# Thêm vào app/api/admin/charts.py:
from datetime import datetime, timedelta

COHORT_SQL = text("""
WITH user_cohorts AS (
  SELECT user_id, DATE_TRUNC('week', created_at)::date AS cohort_week
  FROM users
  WHERE created_at >= NOW() - (:weeks * 7 || ' days')::interval
),
weekly_activity AS (
  SELECT DISTINCT user_id, DATE_TRUNC('week', created_at)::date AS active_week
  FROM messages
),
cohort_size AS (
  SELECT cohort_week, COUNT(*) AS size FROM user_cohorts GROUP BY cohort_week
)
SELECT
  uc.cohort_week,
  cs.size,
  ((wa.active_week - uc.cohort_week) / 7)::int AS week_offset,
  COUNT(DISTINCT uc.user_id) AS retained
FROM user_cohorts uc
JOIN weekly_activity wa ON uc.user_id = wa.user_id
JOIN cohort_size cs ON uc.cohort_week = cs.cohort_week
WHERE wa.active_week >= uc.cohort_week
GROUP BY uc.cohort_week, cs.size, week_offset
ORDER BY uc.cohort_week DESC, week_offset
""")

@router.get("/cohort-retention")
async def cohort_retention(
    weeks: int = Query(8, ge=2, le=24),
    admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    cache_key = f"admin:chart:cohort:{weeks}"
    cached = r.get(cache_key)
    if cached: return json.loads(cached)

    rows = list(db.execute(COHORT_SQL, {"weeks": weeks}))
    today = datetime.now().date()
    today_week = today - timedelta(days=today.weekday())

    cohorts_map = {}
    for row in rows:
        cw = row.cohort_week
        if cw not in cohorts_map:
            cohorts_map[cw] = {
                "cohort_week": str(cw),
                "cohort_size": row.size,
                "retention": {},
            }
        pct = round(row.retained * 100 / row.size) if row.size else 0
        cohorts_map[cw]["retention"][f"w{row.week_offset}"] = pct

    # Fill null cho weeks chưa diễn ra
    for cw, cohort in cohorts_map.items():
        weeks_since = (today_week - cw).days // 7
        for w in range(0, weeks):
            key = f"w{w}"
            if w > weeks_since:
                cohort["retention"][key] = None
            elif key not in cohort["retention"]:
                cohort["retention"][key] = 0

    result = {"cohorts": list(cohorts_map.values())}
    r.setex(cache_key, 86400, json.dumps(result, default=str))
    return result
```

**Test scenarios**:
- TC1: Cohort tuần hiện tại → w0=100%, w1-w7 = null.
- TC2: Retention non-increasing trong 1 cohort.
- TC3: Performance <500ms với 50 user.

---

## Epic 3: User Management APIs

**Goal**: Cho phép admin tìm kiếm, xem chi tiết, và quản lý từng user.

**Stories**: 3 · **Size**: ~9 SP

---

### Story 3.1: User list endpoint với search/filter/pagination

**Type**: Story · **Size**: L · **Labels**: backend, api, db
**Depends on**: 1.3, 2.4
**Sprint**: 2

**User story**:
As an admin, I want to list all users with search/filter/sort/pagination.

**Acceptance Criteria**:
- [ ] `GET /api/admin/users` với query params: `search`, `tier`, `status`, `sort`, `limit`, `offset`.
- [ ] Search trên `user_id`, `display_name`, `telegram_username` (ILIKE).
- [ ] Sort: `last_active_desc` (default), `cost_desc`, `joined_desc`, `messages_desc`.
- [ ] `display_name` luôn masked initials.
- [ ] `last_active_human` localize tiếng Việt.

**Implementation Skeleton**:

📁 Files: `app/api/admin/users.py`, `app/utils/pii.py`, `app/utils/time_human.py`

```python
# app/utils/pii.py
def mask_name(full_name: str) -> str:
    """Nguyễn Văn An → Nguyễn V. A."""
    if not full_name: return "—"
    parts = full_name.strip().split()
    if len(parts) == 1: return parts[0]
    return parts[0] + " " + " ".join(p[0].upper() + "." for p in parts[1:])
```

```python
# app/utils/time_human.py
from datetime import datetime, timezone

def humanize_vi(dt: datetime | None) -> str:
    if not dt: return "Chưa hoạt động"
    now = datetime.now(timezone.utc)
    s = int((now - dt).total_seconds())
    if s < 60: return "vừa xong"
    if s < 3600: return f"{s // 60} phút trước"
    if s < 86400: return f"{s // 3600} giờ trước"
    if s < 604800: return f"{s // 86400} ngày trước"
    return f"{s // 604800} tuần trước"
```

```python
# app/api/admin/users.py
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.admin.deps import get_current_admin
from app.utils.pii import mask_name
from app.utils.time_human import humanize_vi
from app.services.tier_classifier import classify_tier
from app.services.admin_audit import log_action

router = APIRouter(prefix="/users", tags=["admin-users"])

USER_LIST_SQL = """
WITH user_stats AS (
  SELECT
    u.user_id, u.display_name, u.telegram_username, u.created_at,
    u.manual_status,
    MAX(m.created_at) AS last_active_at,
    COUNT(m.id) AS messages_total,
    COALESCE(SUM(l.tokens_total), 0) AS tokens_total,
    COALESCE(SUM(l.cost_usd), 0) AS llm_cost_total_usd,
    (SELECT COUNT(*) FROM assets a
     WHERE a.user_id = u.user_id AND a.deleted_at IS NULL) AS assets_count,
    (SELECT COALESCE(SUM(current_value_vnd), 0) FROM assets a
     WHERE a.user_id = u.user_id AND a.deleted_at IS NULL) AS total_asset_vnd
  FROM users u
  LEFT JOIN messages m ON u.user_id = m.user_id
  LEFT JOIN llm_calls l ON u.user_id = l.user_id
  WHERE 1=1 {search_clause}
  GROUP BY u.user_id, u.display_name, u.telegram_username, u.created_at, u.manual_status
)
SELECT * FROM user_stats
ORDER BY {order_clause}
LIMIT :limit OFFSET :offset
"""

ORDER_MAP = {
    "last_active_desc": "last_active_at DESC NULLS LAST",
    "cost_desc": "llm_cost_total_usd DESC",
    "joined_desc": "created_at DESC",
    "messages_desc": "messages_total DESC",
}

def classify_status(created_at, last_active_at, manual_status) -> str:
    if manual_status: return manual_status
    now = datetime.now(timezone.utc)
    if (now - created_at) < timedelta(days=3): return "new"
    if not last_active_at or (now - last_active_at) > timedelta(days=7):
        return "dormant"
    if (now - last_active_at) > timedelta(days=3): return "at_risk"
    return "active"

@router.get("")
async def list_users(
    search: str | None = Query(None),
    tier: str | None = Query(None),
    status: str | None = Query(None),
    sort: str = Query("last_active_desc"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    search_clause = ""
    params = {"limit": limit, "offset": offset}
    if search:
        search_clause = """AND (u.user_id ILIKE :search
                            OR u.display_name ILIKE :search
                            OR u.telegram_username ILIKE :search)"""
        params["search"] = f"%{search}%"

    order_clause = ORDER_MAP.get(sort, ORDER_MAP["last_active_desc"])
    sql = USER_LIST_SQL.format(search_clause=search_clause, order_clause=order_clause)
    rows = list(db.execute(text(sql), params))

    users = []
    for row in rows:
        user_tier = classify_tier(float(row.total_asset_vnd or 0))
        user_status = classify_status(row.created_at, row.last_active_at,
                                       row.manual_status)
        if tier and user_tier != tier: continue
        if status and user_status != status: continue
        users.append({
            "user_id": row.user_id,
            "display_name": mask_name(row.display_name or row.telegram_username or row.user_id),
            "tier": user_tier,
            "joined_at": row.created_at.date().isoformat(),
            "last_active_at": row.last_active_at.isoformat() if row.last_active_at else None,
            "last_active_human": humanize_vi(row.last_active_at),
            "messages_total": row.messages_total,
            "tokens_total": int(row.tokens_total or 0),
            "llm_cost_total_usd": float(row.llm_cost_total_usd or 0),
            "assets_count": row.assets_count,
            "status": user_status,
        })

    return {"total": len(users), "limit": limit, "offset": offset, "users": users}
```

**Test scenarios**:
- TC1: Search "Nguyễn" → trả users match.
- TC2: Filter `status=dormant` → chỉ user >7 ngày inactive.
- TC3: Pagination limit=10 offset=10 → trả user 11-20.
- TC4: `display_name` không bao giờ trả full name.

---

### Story 3.2: User detail endpoint

**Type**: Story · **Size**: M · **Labels**: backend, api, service
**Depends on**: 3.1
**Sprint**: 2

**Acceptance Criteria**:
- [ ] `GET /api/admin/users/{user_id}` trả đầy đủ profile + analytics.
- [ ] Activity timeline 30 ngày.
- [ ] Asset breakdown by type.
- [ ] LLM cost breakdown by intent.
- [ ] License info (placeholder).
- [ ] Audit log mỗi lần view.
- [ ] PII default masked, `?reveal=true` để unmask (log audit `pii_revealed`).

**Implementation Skeleton**:

```python
# Thêm vào app/api/admin/users.py:

@router.get("/{user_id}")
async def user_detail(
    user_id: str,
    request: Request,
    reveal: bool = Query(False),
    admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.execute(text("SELECT * FROM users WHERE user_id = :uid"),
                     {"uid": user_id}).first()
    if not user:
        raise HTTPException(404, "User not found")

    log_action(db, admin.id, "view_user_detail",
              target_type="user", target_id=user_id, request=request)
    if reveal:
        log_action(db, admin.id, "pii_revealed",
                  target_type="user", target_id=user_id, request=request)

    timeline = db.execute(text("""
        SELECT DATE(created_at) AS d, COUNT(*) AS c FROM messages
        WHERE user_id = :uid AND created_at >= NOW() - INTERVAL '30 days'
        GROUP BY DATE(created_at) ORDER BY d
    """), {"uid": user_id})

    assets = db.execute(text("""
        SELECT asset_type, COUNT(*) AS c, SUM(current_value_vnd) AS total_value
        FROM assets WHERE user_id = :uid AND deleted_at IS NULL
        GROUP BY asset_type
    """), {"uid": user_id})

    cost_by_intent = db.execute(text("""
        SELECT m.resolved_by, COUNT(l.id) AS calls, SUM(l.cost_usd) AS total_cost
        FROM messages m
        LEFT JOIN llm_calls l ON l.message_id = m.id
        WHERE m.user_id = :uid AND m.created_at >= NOW() - INTERVAL '30 days'
        GROUP BY m.resolved_by
    """), {"uid": user_id})

    license = db.execute(text(
        "SELECT plan, status, trial_ends_at FROM licenses WHERE user_id = :uid"
    ), {"uid": user_id}).first()

    full_name = user.display_name
    return {
        "user_id": user.user_id,
        "display_name": full_name if reveal else mask_name(full_name),
        "telegram_username": user.telegram_username,
        "joined_at": user.created_at.isoformat(),
        "timeline": [{"date": str(r.d), "messages": r.c} for r in timeline],
        "assets": [{"type": r.asset_type, "count": r.c,
                     "total_value_vnd": int(r.total_value or 0)} for r in assets],
        "cost_by_intent": [{"resolved_by": r.resolved_by, "calls": r.calls,
                             "total_cost_usd": float(r.total_cost or 0)}
                            for r in cost_by_intent],
        "license": {
            "plan": license.plan if license else "free",
            "status": license.status if license else "active",
            "trial_ends_at": license.trial_ends_at.isoformat()
                if license and license.trial_ends_at else None,
        },
    }
```

**Test scenarios**:
- TC1: Valid user_id → response đầy đủ fields.
- TC2: User không tồn tại → 404.
- TC3: `reveal=true` → audit log có `pii_revealed`.
- TC4: Mỗi lần view → audit log entry `view_user_detail`.

---

### Story 3.3: User status change action

**Type**: Story · **Size**: S · **Labels**: backend, api, security
**Depends on**: 3.2, 1.4
**Sprint**: 2

**Acceptance Criteria**:
- [ ] `PATCH /api/admin/users/{user_id}/status` body `{status, reason}`.
- [ ] Status allowed: `active`, `suspended`.
- [ ] Suspended user không tương tác được với bot.
- [ ] Audit log đầy đủ (from/to/reason).
- [ ] Reason required, min 10 chars.

**Implementation Skeleton**:

```python
# Migration thêm cột users.manual_status:
def upgrade():
    op.add_column("users", sa.Column("manual_status", sa.String(50), nullable=True))
```

```python
# Thêm vào app/api/admin/users.py:
from pydantic import BaseModel, Field

class StatusChangeRequest(BaseModel):
    status: str = Field(..., pattern="^(active|suspended)$")
    reason: str = Field(..., min_length=10, max_length=500)

@router.patch("/{user_id}/status")
async def change_status(
    user_id: str, body: StatusChangeRequest, request: Request,
    admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.execute(text(
        "SELECT user_id, manual_status FROM users WHERE user_id = :uid"
    ), {"uid": user_id}).first()
    if not user: raise HTTPException(404)

    old_status = user.manual_status or "active"
    new_status = body.status if body.status == "suspended" else None
    db.execute(text("UPDATE users SET manual_status = :s WHERE user_id = :uid"),
              {"s": new_status, "uid": user_id})
    db.commit()

    log_action(db, admin.id, "user_status_changed",
              target_type="user", target_id=user_id,
              payload={"from": old_status, "to": body.status, "reason": body.reason},
              request=request)
    return {"user_id": user_id, "status": body.status}

# Trong bot message handler, check status:
def is_user_allowed(user_id, db):
    row = db.execute(text("SELECT manual_status FROM users WHERE user_id = :uid"),
                    {"uid": user_id}).first()
    return not row or row.manual_status != "suspended"
```

**Test scenarios**:
- TC1: Suspend user → bot reject message.
- TC2: Unsuspend → user dùng lại bình thường.
- TC3: Reason 5 chars → 422.
- TC4: Audit log có from/to status và reason.

---

## Epic 4: Frontend Foundation

**Goal**: Setup project Vite, auth flow, layout chung.

**Stories**: 3 · **Size**: ~8 SP

> Reference: dashboard prototype JSX (`be_tien_admin_dashboard.jsx`) đã có sẵn — phần lớn component code reuse được.

---

### Story 4.1: Vite project setup + Tailwind + design tokens

**Type**: Story · **Size**: M · **Labels**: frontend, infra
**Depends on**: —
**Sprint**: 2

**Acceptance Criteria**:
- [ ] `npm create vite@latest betien-admin -- --template react`.
- [ ] Install: `recharts`, `lucide-react`, `tailwindcss`, `react-router-dom`.
- [ ] Tailwind config với design tokens theo Section 9.4 detailed doc.
- [ ] Fonts Fraunces, Geist, JetBrains Mono qua Google Fonts trong `index.html`.
- [ ] `vite.config.js`: proxy `/api` → `localhost:8000` cho dev.
- [ ] README với instructions install/dev/build.

**Test scenarios**:
- TC1: `npm run dev` → mở localhost:5173 không error.
- TC2: `npm run build` → `dist/` tạo thành công.
- TC3: Class `text-gold` render #B8945A.

---

### Story 4.2: Auth flow (login + protected routes + change password)

**Type**: Story · **Size**: L · **Labels**: frontend, auth
**Depends on**: 4.1, 1.2, 1.3
**Sprint**: 2

**Acceptance Criteria**:
- [ ] `src/api/client.js` fetch wrapper (Section 9.3 detailed).
- [ ] Token lưu trong localStorage.
- [ ] `AuthProvider` context wrap toàn app.
- [ ] `LoginPage` với error inline, loading state.
- [ ] `ProtectedRoute` component.
- [ ] `ChangePasswordPage` hiện ngay nếu `force_password_change=true`.
- [ ] Auto-logout khi 401.
- [ ] Login page financial editorial aesthetic.

**Test scenarios**:
- TC1: Vào `/` chưa login → redirect login.
- TC2: First login → redirect change password.
- TC3: Sau change password → dashboard.
- TC4: Token expired → auto-logout.

---

### Story 4.3: Dashboard layout (header + hero + grid framework)

**Type**: Story · **Size**: M · **Labels**: frontend, ui
**Depends on**: 4.2
**Sprint**: 2

**Acceptance Criteria**:
- [ ] Header sticky: logo, status, date selector (7d/14d/30d/90d), refresh.
- [ ] Hero: display title + subtitle.
- [ ] Responsive: header collapse mobile, hero font scale.
- [ ] Date range state qua context, propagate xuống charts.

**Test scenarios**:
- TC1: Responsive ≥1024px, 768px, 375px không vỡ.
- TC2: Click refresh → refetch + loading.
- TC3: Change date range → charts update.

---

## Epic 5: Dashboard Components

**Goal**: Build từng widget hiển thị data.

**Stories**: 4 · **Size**: ~14 SP

> Code reference: `be_tien_admin_dashboard.jsx` đã build sẵn các component. Stories này chủ yếu là wire-up data từ API thay vì mock data.

---

### Story 5.1: KPI cards grid

**Type**: Story · **Size**: M · **Labels**: frontend, ui
**Depends on**: 4.3, 2.1
**Sprint**: 3

**Acceptance Criteria**:
- [ ] `KPICard` component nhận props: `label`, `value`, `unit`, `delta`, `accent`.
- [ ] Hero number Fraunces 36-48px font-semibold.
- [ ] Delta arrow + color (sage positive, burgundy negative).
- [ ] Cost delta: âm = good.
- [ ] Accent bar 12px top-left.
- [ ] Grid: 6/3/2 cols (desktop/tablet/mobile).
- [ ] Loading skeleton.
- [ ] Empty state: "—".
- [ ] Fetch `/api/admin/stats/overview`.

---

### Story 5.2: Growth charts (User growth + DAU)

**Type**: Story · **Size**: M · **Labels**: frontend, ui, charts
**Depends on**: 4.3, 2.2
**Sprint**: 3

**Acceptance Criteria**:
- [ ] `UserGrowthChart`: AreaChart, gold gradient, 30 ngày.
- [ ] `DAUChart`: BarChart, ink-900 bars, 14 ngày.
- [ ] Tooltip custom styled (white bg, hairline border).
- [ ] Grid 2/3 + 1/3 desktop, stack mobile.
- [ ] Title (Fraunces 18px) + subtitle (Geist 12px) cho mỗi card.

---

### Story 5.3: Distribution charts + Cohort table

**Type**: Story · **Size**: L · **Labels**: frontend, ui, charts
**Depends on**: 4.3, 2.3, 2.4, 2.5
**Sprint**: 3

**Acceptance Criteria**:
- [ ] `FeatureClicksChart`: horizontal bar, gold.
- [ ] `IntentBreakdownChart`: donut + legend + insight footer.
- [ ] `TierDistributionChart`: donut với 4 tier gradient.
- [ ] `CohortRetentionTable`: heatmap, cell opacity tỉ lệ với retention %.
  - Cell text white khi bg đậm, ink-900 khi nhạt.
  - Null cells để trống.
- [ ] Insight footer (1-2 dòng) cho mỗi chart.

---

### Story 5.4: User directory table

**Type**: Story · **Size**: L · **Labels**: frontend, ui
**Depends on**: 4.3, 3.1, 3.2
**Sprint**: 3

**Acceptance Criteria**:
- [ ] Table columns: User ID/Name, Tier, Joined, Last Active, Messages, Tokens, LLM Cost, Assets, Status, Action.
- [ ] Search debounced 300ms.
- [ ] Filter Tier + Status dropdown.
- [ ] Click column header → sort.
- [ ] Click row → user detail modal/drawer.
- [ ] Status badge với color rule (active/at-risk/dormant/new).
- [ ] User 0 asset → cột Assets màu burgundy.
- [ ] Pagination 50/page.
- [ ] Mobile: hide secondary columns.
- [ ] User detail modal: timeline mini chart, asset breakdown, cost breakdown.
- [ ] Modal có button "Suspend user" (gọi Story 3.3 endpoint).

---

## Epic 6: Security & Deployment

**Stories**: 3 · **Size**: ~7 SP

---

### Story 6.1: Caddy + HTTPS + CORS + rate limit

**Type**: Story · **Size**: M · **Labels**: infra, security
**Depends on**: 1.3
**Sprint**: 3

**Acceptance Criteria**:
- [ ] Caddy config cho `admin.betien.vn` theo Section 12.3.
- [ ] Auto-SSL từ Let's Encrypt.
- [ ] CORS chỉ allow `admin.betien.vn`.
- [ ] Rate limit 100 req/min/IP cho `/api/admin/*`.
- [ ] Security headers: HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy.
- [ ] DNS A record subdomain.

**Implementation Skeleton**:

```python
# app/main.py — CORS setup
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://admin.betien.vn"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
```

```caddyfile
# /etc/caddy/Caddyfile
admin.betien.vn {
    tls phuongphh@nuitruc.ai

    handle /api/* {
        reverse_proxy localhost:8000
    }
    handle {
        reverse_proxy localhost:8000
    }

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
    }
}
```

**Test scenarios**:
- TC1: `https://admin.betien.vn` load cert hợp lệ.
- TC2: 150 req/min từ 1 IP → 100 đầu OK, 50 sau 429.
- TC3: CORS từ origin khác → block.

---

### Story 6.2: PII protection layer

**Type**: Story · **Size**: S · **Labels**: backend, security
**Depends on**: 3.1
**Sprint**: 3

**Acceptance Criteria**:
- [ ] Helpers `mask_name`, `mask_email`, `mask_phone`.
- [ ] Áp dụng default mọi admin endpoint.
- [ ] User detail có `?reveal=true` (audit log).

**Implementation Skeleton**:

```python
# app/utils/pii.py (extended từ Story 3.1)
import re

def mask_name(full_name: str) -> str:
    if not full_name: return "—"
    parts = full_name.strip().split()
    if len(parts) == 1: return parts[0]
    return parts[0] + " " + " ".join(p[0].upper() + "." for p in parts[1:])

def mask_email(email: str) -> str:
    if not email or "@" not in email: return "—"
    local, domain = email.split("@", 1)
    if len(local) <= 2: return f"{local[0]}***@{domain}"
    return f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}@{domain}"

def mask_phone(phone: str) -> str:
    if not phone: return "—"
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 7: return "***"
    return f"{digits[:3]}{'*' * (len(digits) - 6)}{digits[-3:]}"
```

**Test scenarios**:
- TC1: `mask_name("Nguyễn Văn An")` = "Nguyễn V. A.".
- TC2: `mask_email("phuongphh@nuitruc.ai")` = "p********h@nuitruc.ai".
- TC3: `mask_phone("0987654321")` = "098****321".

---

### Story 6.3: Production deployment workflow + smoke test

**Type**: Story · **Size**: M · **Labels**: infra, deployment
**Depends on**: 6.1, all Epic 5
**Sprint**: 3

**Acceptance Criteria**:
- [ ] `DEPLOY.md` với step-by-step.
- [ ] Smoke test checklist 10 items.
- [ ] Rollback procedure.

**Implementation Skeleton**:

```bash
# scripts/deploy_admin.sh
#!/usr/bin/env bash
set -euo pipefail

echo "=== Bé Tiền Admin Console Deploy ==="

echo "→ Apply migrations..."
alembic upgrade head

echo "→ Seed initial admin..."
python -m scripts.seed_admin

echo "→ Build frontend..."
(cd betien-admin && npm install && npm run build)

echo "→ Copy static files..."
rm -rf app/static/admin/*
mkdir -p app/static/admin
cp -r betien-admin/dist/* app/static/admin/

echo "→ Restart FastAPI..."
systemctl restart betien-api  # adjust to your service name

echo "→ Reload Caddy..."
caddy reload --config /etc/caddy/Caddyfile

echo "✓ Deploy complete. Run smoke test next."
```

**Smoke test checklist** (manual, từ DEPLOY.md):
1. Open `https://admin.betien.vn` → redirect `/login`
2. Login `phuongphh@nuitruc.ai/admin` → redirect change password
3. Change password → redirect dashboard
4. 6 KPI cards show data (không phải mock)
5. All 6 charts render
6. User table search + filter work
7. Click user row → detail modal opens
8. Logout → redirect login
9. Direct URL after logout → redirect login (no bypass)
10. Mobile view (375px) → layout intact

**Rollback**:
```bash
# Nếu deploy fail:
git revert HEAD
alembic downgrade -1
./scripts/deploy_admin.sh
```

---

## Epic 7: License Foundation

**Stories**: 1 · **Size**: ~3 SP

---

### Story 7.1: License data model + placeholder UI section

**Type**: Story · **Size**: M · **Labels**: backend, db, frontend
**Depends on**: —
**Sprint**: 3

**Acceptance Criteria**:
- [ ] Migration tạo bảng `licenses` theo Section 8.1.
- [ ] Backfill: tạo license `plan=free, status=active` cho mọi user hiện có.
- [ ] Trigger: user mới đăng ký → auto tạo license free.
- [ ] UI placeholder section: dark card, gold accent, "Coming Phase 5" badge.
- [ ] Liệt kê metrics tương lai dưới dạng tag không clickable.
- [ ] Endpoint `GET /api/admin/licenses/summary` trả counts theo plan.

**Implementation Skeleton**:

```python
# app/models/license.py
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.db.base import Base

class License(Base):
    __tablename__ = "licenses"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(50), unique=True, nullable=False, index=True)
    tenant_id = Column(Integer, nullable=False)
    plan = Column(String(50), nullable=False, default="free")
    status = Column(String(50), nullable=False, default="active")
    trial_started_at = Column(DateTime(timezone=True))
    trial_ends_at = Column(DateTime(timezone=True))
    paid_started_at = Column(DateTime(timezone=True))
    next_renewal_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))
    license_metadata = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())
```

```python
# migrations/versions/XXXX_licenses.py
def upgrade():
    op.create_table("licenses", ...)  # full schema
    # Backfill
    op.execute("""
        INSERT INTO licenses (user_id, tenant_id, plan, status)
        SELECT user_id, COALESCE(tenant_id, 1), 'free', 'active'
        FROM users
        ON CONFLICT (user_id) DO NOTHING
    """)
```

```python
# Trong service tạo user mới (e.g. app/services/user_service.py):
def create_user(db, user_data):
    user = User(**user_data)
    db.add(user)
    db.flush()  # get user.id
    license = License(
        user_id=user.user_id,
        tenant_id=user.tenant_id or 1,
        plan="free",
        status="active",
    )
    db.add(license)
    db.commit()
    return user
```

```python
# app/api/admin/licenses.py
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.admin.deps import get_current_admin

router = APIRouter(prefix="/licenses", tags=["admin-licenses"])

@router.get("/summary")
async def license_summary(
    admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    rows = db.execute(text("SELECT plan, COUNT(*) AS c FROM licenses GROUP BY plan"))
    by_plan = {row.plan: row.c for row in rows}
    return {
        "by_plan": {
            "free": by_plan.get("free", 0),
            "pro": by_plan.get("pro", 0),
            "hnw": by_plan.get("hnw", 0),
        },
        "total": sum(by_plan.values()),
    }
```

**Test scenarios**:
- TC1: Existing users đều có license `plan=free`.
- TC2: User mới đăng ký → license tạo tự động.
- TC3: `/licenses/summary` trả `{free: N, pro: 0, hnw: 0}`.
- TC4: UI placeholder render đúng aesthetic editorial.

---

## Summary

| Epic | Stories | Size | Sprint |
|------|---------|------|--------|
| 1. Backend Foundation & Auth | 4 | ~11 SP | 1 |
| 2. Analytics APIs | 5 | ~14 SP | 1-2 |
| 3. User Management APIs | 3 | ~9 SP | 2 |
| 4. Frontend Foundation | 3 | ~8 SP | 2 |
| 5. Dashboard Components | 4 | ~14 SP | 3 |
| 6. Security & Deployment | 3 | ~7 SP | 3 |
| 7. License Foundation | 1 | ~3 SP | 3 |
| **TOTAL** | **23** | **~66 SP** | **3 sprints** |

### Cross-cutting concerns

- **Audit log**: Mọi mutation endpoint phải log.
- **Multi-tenancy**: Mọi query filter `tenant_id` (single tenant trong v1.0).
- **PII protection**: Default masked, opt-in unmask qua `?reveal=true`.
- **Error format**: `{error: {code, message}}`.
- **Localization**: User-facing tiếng Việt, technical fields tiếng Anh.

### Definition of Done

- [ ] All Acceptance Criteria pass.
- [ ] All test scenarios pass.
- [ ] Code review (self-review nếu solo).
- [ ] Docs updated (API doc, README).
- [ ] Audit log entries verify được (cho mutation).
- [ ] Smoke test local pass.

### Risk register (updated v2.0)

| Risk | Probability | Impact | Mitigation |
|------|-----------|--------|-----------|
| Cohort retention query chậm | Medium | Medium | Cache 24h, materialized view khi >500 user |
| Recharts không render đẹp mobile | Low | Low | Test sớm Story 5.2 |
| ~~Phase 3.5 `resolved_by` column~~ | ~~High~~ | ~~High~~ | ✅ **Resolved 2026-05-02**: Phase 3.5 shipped column với dispatcher set value. Story 1.5 removed (v2.0). |
| Caddy auto-SSL fail (DNS) | Low | Medium | Test DNS trước, fallback Cloudflare Tunnel |
| Backfill license cho nhiều user chậm | Low | Low | Batch insert |
| Admin password "admin" bị brute force trước khi đổi | Medium | High | ✅ **Mitigated**: force_password_change flag (Story 1.1, 1.2) + rate limit (Story 1.2) |
| Phase 4.2 signal surface gap (Day 7 micro-survey, NBA matrix click) | Medium | Low | v1.0 chỉ count via `feature_events`; v1.1 add dedicated panel |

### Order of implementation (recommended)

**Sprint 1 — Foundation + Critical APIs:**
1. Story 1.1 → 1.2 → 1.3 → 1.4 (auth + audit).
2. Story 2.1 → 2.2 → 2.3 (analytics APIs).

**Sprint 2 — Remaining APIs + Frontend Foundation:**
3. Story 2.4 → 2.5 (intent + cohort).
4. Story 3.1 → 3.2 → 3.3 (user management).
5. Story 4.1 → 4.2 → 4.3 (frontend setup).

**Sprint 3 — UI + Security + Deploy:**
6. Story 5.1 → 5.2 → 5.3 → 5.4 (dashboard components).
7. Story 6.2 (PII) song song với UI work.
8. Story 7.1 (license placeholder).
9. Story 6.1 (Caddy/HTTPS) → Story 6.3 (deploy + smoke test) → 🚀

---

**Document version**: 2.0 (renamed Phase 3.6 → 4.2.5, Story 1.5 removed post-Phase 3.5)
**Last updated**: 2026-05-13
**Companion**: `phase-4.2.5-detailed.md`
