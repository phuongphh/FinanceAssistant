# CLAUDE.md — Bé Tiền (Decision Engine)

Source of truth for Claude Code working on this codebase.
Read this before any code changes. For implementation details, open the corresponding phase doc linked below.

**Document version:** 3.0 (compacted from v2.0 to reduce token overhead, 07/05/2026)

---

**Phase status** (auto-synced from
[`docs/current/phase-status.yaml`](docs/current/phase-status.yaml)):

<!-- BEGIN: phase-status:current-line -->
🚀 **First-5-Minutes WOW** (current) — [detail](docs/current/phase-4.4/phase-4.4-detailed.md)
<!-- END: phase-status:current-line -->

For full roadmap, see [`docs/current/phase-status.yaml`](docs/current/phase-status.yaml).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent runtime | OpenClaw (Node.js) → Telegram Bot |
| Backend | FastAPI (Python 3.11+, async) |
| Database | PostgreSQL 16 (Docker local) |
| Cache | Redis |
| Primary LLM | DeepSeek API (text, classify, extract) |
| Vision LLM | Claude API (OCR only) |
| Speech | OpenAI Whisper API |
| Market data | SSI/VNDIRECT (VN stocks), CoinGecko (crypto), SJC/PNJ (gold), bank-rate scrapers, RSS news |
| Dashboard | Notion (one-way read sync from PostgreSQL) |
| Package manager | pip + `backend/requirements.txt` (see note below) |

> **Package manager — reality vs. aspiration (as of 2026-05-24):**
> Production và CI hiện đang dùng **pip** với `backend/requirements.txt`. Prod server có **2 venv tách biệt**:
> - `venv/` — services (backend + scheduler chạy từ launchd plist, xem `launchd/*.plist.template`)
> - `.venv/` — tooling (alembic migration, scripts)
>
> Mỗi lần `requirements.txt` đổi phải `pip install` vào **cả hai** venv (xem `scripts/rebuild-finance-prod.sh`).
> Repo **không có** `pyproject.toml` hay `uv.lock`.
>
> **Khả năng migrate sang `uv` — nên cân nhắc khi có thời gian:**
> - ✅ *Lợi*: install nhanh hơn 10-100×, lock file đảm bảo reproducibility, gộp 2 venv thành 1 `.venv/`, bỏ rủi ro quên install vào 1 venv, modern tooling (workspace, dep groups).
> - ❌ *Chi phí*: convert `requirements.txt` → `pyproject.toml` + sinh `uv.lock`, sửa launchd plist templates trỏ `.venv/`, cập nhật `scripts/install-launchd.sh` + `scripts/rebuild-finance-prod.sh` + `.github/workflows/*.yml`, cài `uv` trên prod server, smoke test toàn bộ flow deploy.
> - 🎯 *Khi nào nên làm*: lúc cần thêm dep groups (dev/test/prod tách biệt) hoặc khi deploy time/dep drift trở thành pain point. Trước đó: giữ pip + dual venv vì đang work.

**Deprecated (V1 → V2):** Gmail API, SMS forwarding — replaced by AI Storytelling (threshold-based capture).

---

## Critical Conventions — NON-NEGOTIABLE

### Money handling
- **Always use `Decimal`**, never `float` for money
- DB columns: `NUMERIC(20,2)` for money, `NUMERIC(15,2)` for smaller amounts
- Format via `currency_utils.format_money_short/full` (e.g., "45k", "1.5tr", "1.2 tỷ")

### Multi-tenancy from day 1
- **Every table has `user_id` (UUID, NOT NULL, indexed)** — even with single user
- Business logic lives in **FastAPI backend**, NOT in OpenClaw Skills
- OpenClaw Skills are **thin wrappers** calling backend API

### Async everywhere
- All I/O (DB, API, file) uses `async/await`
- Type hints mandatory
- Pydantic for data validation
- Use Python `logging`, never `print()`

### Vietnamese localization
- All user-facing strings in `content/*.yaml` (NOT hardcoded in code)
- Test by reading aloud — if cringy or robotic, rewrite
- "Bé Tiền" persona: warm, supportive, NEVER harsh on overspending or past-due
- **Customer-facing positioning:** Bé Tiền is a *người đồng hành quản lý tài sản*
  (companion that helps manage assets). Internal docs use "Decision Engine"
  as shorthand for product positioning (Strategy V4 — "Personal CFO" is
  retired even internally; see `docs/current/strategy.md`). Neither
  "Decision Engine", "GPS tài chính", nor "CFO" may EVER appear in
  user-facing text (welcome bubbles, chart watermarks, briefings, share
  images, public-facing announcement copy) — use *người đồng hành* /
  *quản lý tài sản* instead. Target user per V4: 22-35 tuổi, Level 0→1
  ("thế hệ đang xây"), NOT mass affluent.

### Soft delete pattern
- Never hard-delete user data
- Use `deleted_at` timestamp or `is_active` boolean

---

## Layer Contract — VIOLATING THIS BREAKS PRODUCTION

```
webhook → claim update_id → asyncio.create_task → worker → handler → service → adapter
  (≤100ms)    (Postgres dedup)                      (commit)  (logic)  (flush)  (transport)
```

| Layer | DO | DON'T |
|---|---|---|
| `routers/` | Parse HTTP, dedup `update_id`, enqueue, return 200 | Business logic, LLM call, Telegram send |
| `workers/` | Open session, dispatch, commit **once** at boundary | Business logic |
| `bot/handlers/` | Route intent, extract Telegram data, call service, format response | `db.commit()`, raw DB queries (except view-only) |
| `services/` | Business logic, **flush only**, return domain objects | `db.commit()`, direct Telegram/LLM, read env |
| `adapters/` | Transport: Telegram, Notion, DeepSeek, Claude, Whisper | Business logic |
| `ports/` | Protocol interfaces for `Notifier`, `LLM` (DI/test) | Implementation |

**Consequences:**
- LLM call in webhook path → must be background task (not block webhook response)
- Service NEVER calls `db.commit()` — caller (router/worker) owns transaction boundary
- Service NEVER imports `telegram_service` directly — use `Notifier` port via `get_notifier()`
- LLM cache key includes `user_id` by default; use `shared_cache=True` only for prompts without user data
- All Telegram updates must dedup via `telegram_updates.update_id` before processing

---

## Forbidden Actions

- ❌ Hardcode credentials, commit `.env`, expose secrets
- ❌ Use `float` for money values
- ❌ `db.commit()` in service layer
- ❌ Hardcoded Vietnamese strings in code (use `content/*.yaml`)
- ❌ Read these directories: `tests/fixtures/`, `docs/archive/`, `node_modules/`, `.venv/`
- ❌ Modify migrations already committed and applied
- ❌ Direct `git push origin main` for substantive changes (see [GitHub workflow doc](docs/conventions/github-workflow.md))
- ❌ Direct `git push origin prod` for releases — **always go through a PR** from the release/working branch (e.g. `claude/merge-prod-release-N-XXXX`) into `prod`, even when the user says "merge main into prod". Operator reviews & merges via GitHub UI. No fast-forward push to `prod` from CLI.

---

## Test & Build Commands

```bash
# Local setup (one-time) — create venv and install backend deps
python -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

# Daily commands (assume .venv activated, or prefix with `.venv/bin/`)
pytest                                      # Run all tests
pytest tests/services/wealth/               # Run specific suite
pytest tests/prompts/                       # Run LLM prompt tests
ruff check .                                # Lint
ruff format .                               # Format
alembic upgrade head                        # Apply migrations
alembic revision --autogenerate -m "msg"    # Create migration
docker-compose up -d                        # Start PostgreSQL + Redis
```

> Prod deploy script (`scripts/rebuild-finance-prod.sh`) installs into both `venv/` (service) and `.venv/` (tooling). See _Package manager_ note in Tech Stack section.

---

## Documentation References

This file is a **table of contents**, not an encyclopedia. When you need detail, read:

- **Strategy & vision:** [`docs/current/strategy.md`](docs/current/strategy.md) — Ladder of Engagement, positioning, V2 pivot rationale
- **Recently completed phase:** [`docs/current/phase-4.3/phase-4.3-detailed.md`](docs/current/phase-4.3/phase-4.3-detailed.md) — Twin enhancement (weather metaphor + story-first), habit loop, Twin admin dashboard
- **Next phase:** Phase 5.0 — Encryption End-to-End (after June 2026 soft launch)
- **Database schema:** Read latest migrations in `alembic/versions/` for current state
- **Architecture decisions:** [`docs/architecture/`](docs/architecture/) — layer contract rationale, scaling decisions
- **GitHub workflow:** [`docs/conventions/github-workflow.md`](docs/conventions/github-workflow.md) — PR conventions, sub-issue hierarchy, branch naming
- **Coding conventions:** [`docs/conventions/coding.md`](docs/conventions/coding.md) — full Python/API/security details
- **Scale roadmap:** [`docs/strategy/scale-roadmap.md`](docs/strategy/scale-roadmap.md) — Phase 1-4 scale plans
- **V1→V2 migration:** [`docs/archive/MIGRATION_NOTES.md`](docs/archive/MIGRATION_NOTES.md) — historical context only

---

## Available Subagents

Subagents in `.claude/agents/` run in isolated context windows and return concise summaries. Trust their `description` fields — Claude will spawn them when appropriate.

Quick reference:
- `code-explorer` (Haiku) — read/search/summarize files; use BEFORE making changes
- `intent-mapper` (Haiku) — map intent flow through services/templates
- `test-runner` (Haiku) — parse verbose pytest failures into compact reports
- `prompt-tester` (Sonnet) — test LLM prompts (storytelling, classification, advisory) for quality and persona
- `vi-localization-checker` (Haiku) — verify Vietnamese strings, content YAML completeness, Bé Tiền persona consistency
- `layer-contract-checker` (Haiku) — verify code adheres to layer contract above

**Note:** GitHub PR reviews are handled by Claude + ChatGPT bots — no in-session code-reviewer agent needed. Architectural decisions are made directly by main session.

---

## Phase 4.3 — Status: DONE ✅

**Status:** ✅ Implementation complete. Phase 4.3 turned the Financial Twin from a hard-to-grasp feature into a habit-forming experience, and added a Twin admin dashboard. 4 Epics / 15 stories.

### Shipped in Phase 4.3

- **Weather metaphor** thay P10/P50/P90 — 🌧️ Khiêm tốn / ⛅ Bình thường / ☀️ Lạc quan — để người dùng hiểu probability cone mà không cần đọc số percentile.
- **Life-outcome translation** + **story-first narrative** (4-5 màn swipe) + **mascot personification** giúp Twin kể chuyện thay vì bày số liệu.
- **Habit loop**: on-demand recompute (<5s) + causality ("vì sao thay đổi") + action prompt + negative delta handling + delta threshold + return tease để kéo người dùng quay lại.
- **Twin admin dashboard** 4 sections: engagement funnel, loop health, comprehension, delta distribution.

### Next phase

Phase 5.0 — Encryption End-to-End (sau soft launch June 2026).

Detail: [`docs/current/phase-4.3/phase-4.3-detailed.md`](docs/current/phase-4.3/phase-4.3-detailed.md)

## Active Breaking Changes

(None currently — Phase 4.3 is additive over 4.2.5)

When breaking changes are active, list them here with migration path. Move to `docs/archive/` once complete.

---

## When You Discover Design Issues

If implementing reveals a design flaw in this CLAUDE.md or referenced docs:

1. Note the issue inline in your response: `<!-- DESIGN ISSUE: ... -->`
2. Don't silently work around it — surface it to the user
3. Suggest fix or escalate

This file evolves. If a rule fires twice for the same problem, add a note. If the rule never fires, consider removing it.

---

*Document version: 3.0 — compacted to reduce token overhead*  
*Last major update: 07/05/2026 — refactored from 1,340 lines to ~190 lines*  
*Update only when architecture rules change*
