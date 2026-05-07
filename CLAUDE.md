# CLAUDE.md — Personal CFO Assistant

Source of truth for Claude Code working on this codebase.
Read this before any code changes. For implementation details, open the corresponding phase doc linked below.

**Document version:** 3.0 (compacted from v2.0 to reduce token overhead, 07/05/2026)

---

**Phase status** (auto-synced from
[`docs/current/phase-status.yaml`](docs/current/phase-status.yaml)):

<!-- BEGIN: phase-status:current-line -->
🚀 **Phase 3.7: Agent Architecture** (current) — [detail](docs/current/phase-3.7-detailed.md)
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
| Market data | vnstock (stocks), CoinGecko (crypto), SJC scrape (gold), cafef scrape (funds) |
| Dashboard | Notion (one-way read sync from PostgreSQL) |
| Package manager | uv |

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

---

## Test & Build Commands

```bash
uv sync                                     # Install dependencies
uv run pytest                               # Run all tests
uv run pytest tests/services/wealth/        # Run specific suite
uv run pytest tests/prompts/                # Run LLM prompt tests
uv run ruff check .                         # Lint
uv run ruff format .                        # Format
alembic upgrade head                        # Apply migrations
alembic revision --autogenerate -m "msg"    # Create migration
docker-compose up -d                        # Start PostgreSQL + Redis
```

---

## Documentation References

This file is a **table of contents**, not an encyclopedia. When you need detail, read:

- **Strategy & vision:** [`docs/current/strategy.md`](docs/current/strategy.md) — Ladder of Engagement, positioning, V2 pivot rationale
- **Current phase:** [`docs/current/phase-3.8.5-detailed.md`](docs/current/phase-3.8.5-detailed.md) — Phase 3.8.5 implementation & test plan
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

## Phase 3.8.5 — Current Status: TESTING 🧪

**Status:** ✅ Implementation complete. Currently in testing phase before promoting to "done" and moving to next phase.

### Recently shipped — Phase 3.8 (✅ done)
Goals system with `goals.*` schema migration. 6 readers updated for backwards compatibility:
`notion_sync`, `market_service`, `report_service`, `memory_moments`, `query_goals` intent handler, `advisory` intent handler.
Field renames: `goal_name → goals.*`, `deadline → date`, `is_active → status field`.
Stable `FeasibilityBand` enum (replaces localized text). 44 new tests added (total 1527).

### Phase 3.8.5 — _(TODO: fill in 1-line summary)_

> **For maintainer:** Update this section with Phase 3.8.5 specifics. Suggested fields:
> - **Goal:** What this phase delivers
> - **Scope:** What's IN, what's OUT
> - **Key changes:** New services, new intents, schema changes
> - **Test focus:** What testing must verify

### Testing focus

While Phase 3.8.5 is in testing, Claude Code should prioritize:

1. **Regression checks** — verify Phase 3.x intent handlers still work end-to-end
2. **Vietnamese localization** — run `vi-localization-checker` subagent on changed user-facing code
3. **Layer contract** — run `layer-contract-checker` on new services/handlers
4. **Prompt quality** — run `prompt-tester` if any LLM prompts changed
5. **Test coverage** — verify new code paths have tests; aim to keep total ≥1527

### Exit criteria — to ship Phase 3.8.5

- [ ] All unit + integration tests pass (`uv run pytest`)
- [ ] No regressions in Phase 3.x intent handlers
- [ ] Vietnamese localization verified (no hardcoded strings, persona consistent)
- [ ] Layer contract clean (no critical violations)
- [ ] Manual smoke test on Telegram: storytelling, morning briefing, advisory, goals query
- [ ] Update `phase-status.yaml`: status `testing → done`, add next phase as `current`

Detail: [`docs/current/phase-3.8.5-detailed.md`](docs/current/phase-3.8.5-detailed.md)

---

## Active Breaking Changes

(None currently — Phase 3.8.5 is additive over 3.8)

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
