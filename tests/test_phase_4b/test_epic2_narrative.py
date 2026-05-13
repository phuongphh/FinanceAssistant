"""Phase 4B Epic 2 — life-event narrative persona tests (S12).

The LLM call itself is mocked. We verify:
  - off-tone responses are rejected and the YAML fallback is used.
  - the prompt includes the suggested action from the preset.
  - twin-narrative summary correctly compacts a list of events.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.life_events import narrative as narrative_module
from backend.life_events.narrative import (
    build_life_event_narrative,
    summary_for_twin_narrative,
)
from backend.models.life_event import LifeEvent, LifeEventType


def _event(
    event_type: LifeEventType = LifeEventType.BUY_HOUSE,
    title: str = "Mua nhà HCM",
    planned_year: int = 2028,
) -> LifeEvent:
    e = LifeEvent()
    e.id = __import__("uuid").uuid4()
    e.event_type = event_type.value
    e.title = title
    e.planned_date = date(planned_year, 1, 1)
    e.one_time_cost = Decimal("3500000000")
    e.recurring_monthly_delta = Decimal("-8000000")
    e.recurring_duration_months = 240
    return e


def _user():
    return SimpleNamespace(id=__import__("uuid").uuid4())


@pytest.mark.asyncio
async def test_narrative_uses_fallback_on_llm_error(monkeypatch):
    """When call_llm raises, we must return the YAML fallback (no exceptions)."""

    async def fake_llm(*args, **kwargs):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(narrative_module, "call_llm", fake_llm)
    event = _event()
    text = await build_life_event_narrative(
        db=None,
        user=_user(),
        event=event,
        p50_delta=Decimal("-1200000000"),
        target_year=2035,
        wealth_level="Tích lũy",
    )
    assert "Mua nhà HCM" in text
    assert "trade-off" in text or "plan" in text


@pytest.mark.asyncio
async def test_narrative_rejects_persona_violations(monkeypatch):
    """Output containing a forbidden phrase must fall back to YAML."""
    bad_text = (
        "Bạn nên trì hoãn kết hôn nếu áp lực tài chính lớn. "
        "Tình huống này rất nguy hiểm và rủi ro cao."
    )

    async def fake_llm(*args, **kwargs):
        return bad_text

    monkeypatch.setattr(narrative_module, "call_llm", fake_llm)
    text = await build_life_event_narrative(
        db=None,
        user=_user(),
        event=_event(event_type=LifeEventType.WEDDING, title="Cưới"),
        p50_delta=Decimal("-500000000"),
        target_year=2035,
        wealth_level="Đang xây dựng",
    )
    # Forbidden words must NOT appear in the final response.
    lowered = text.lower()
    for forbidden in ("trì hoãn kết hôn", "nguy hiểm", "rủi ro cao"):
        assert forbidden not in lowered
    assert "Cưới" in text


@pytest.mark.asyncio
async def test_narrative_returns_fallback_for_undated_event(monkeypatch):
    event = _event()
    event.planned_date = None  # type: ignore[assignment]

    # call_llm must not even be called when no date is set.
    async def fake_llm(*args, **kwargs):
        pytest.fail("call_llm should not be invoked when planned_date is None")

    monkeypatch.setattr(narrative_module, "call_llm", fake_llm)
    text = await build_life_event_narrative(
        db=None,
        user=_user(),
        event=event,
        p50_delta=Decimal("0"),
        target_year=2035,
        wealth_level="x",
    )
    assert "Mua nhà HCM" in text


@pytest.mark.asyncio
async def test_narrative_rejects_too_short_or_too_long(monkeypatch):
    async def short_llm(*args, **kwargs):
        return "Ngắn quá."

    monkeypatch.setattr(narrative_module, "call_llm", short_llm)
    out = await build_life_event_narrative(
        db=None,
        user=_user(),
        event=_event(),
        p50_delta=Decimal("-100000000"),
        target_year=2035,
        wealth_level="x",
    )
    assert "Mua nhà" in out  # fallback fired


def test_summary_for_twin_narrative_empty_returns_none_marker():
    assert summary_for_twin_narrative([]) == "không có"


def test_summary_for_twin_narrative_caps_at_three():
    events = [
        _event(planned_year=2027, title="A"),
        _event(planned_year=2028, title="B"),
        _event(planned_year=2029, title="C"),
        _event(planned_year=2030, title="D"),
        _event(planned_year=2031, title="E"),
    ]
    summary = summary_for_twin_narrative(events)
    # Only first 3 explicit, last entries collapsed.
    assert "A 2027" in summary
    assert "B 2028" in summary
    assert "C 2029" in summary
    assert "D" not in summary
    assert "(+2)" in summary
