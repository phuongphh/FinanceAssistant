"""Life Events module — Phase 4B Epic 2.

Lets users plan real-life milestones (mua nhà, đám cưới, sinh con, học phí ĐH,
nghỉ hưu sớm, hoặc tùy chỉnh) and see their impact on the Financial Twin's
probability cone. The MC engine in ``backend/twin/engine/life_events.py``
injects deterministic cashflow shocks into all Monte Carlo paths so each
event shows up in cone/optimal projections.

Layer contract:
- ``service.py`` only flushes — caller owns transaction boundary.
- Telegram surface in ``backend/bot/handlers/life_event_entry.py``.
- HTTP surface in ``backend/routers/life_events.py``.
- Vietnamese copy lives in ``content/life_events.yaml`` (never hardcoded).
"""
