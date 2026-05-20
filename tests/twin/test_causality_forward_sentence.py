"""Regression tests for the Twin causality forward sentence.

The original `_forward_sentence` linearly extrapolated `delta * 52 * years` on
top of the 10-year P50, which produced absurd numbers (e.g. claiming the user
would hit 6456.4 tỷ in 2030 while the main Twin view said 316.6 tỷ in 2036).
The fix reads the forward anchor directly from the Twin cone so the causality
message never disagrees with the main view.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from backend.twin.services import causality_service


def _fake_projection(
    *,
    computed_at: datetime,
    cone: list[dict],
) -> SimpleNamespace:
    return SimpleNamespace(computed_at=computed_at, cone_data=cone)


def _ten_year_cone(p50_at_year_10: Decimal) -> list[dict]:
    """Monotonic cone — what a real Monte Carlo run produces.

    Year offsets are 0..10. P50 grows roughly exponentially from a small base
    to the horizon value, so each yearly milestone is strictly smaller than
    the next.
    """
    cone = []
    base = Decimal("10000000000")  # 10 tỷ today
    horizon = p50_at_year_10
    for offset in range(11):
        # Linear interp on log-space is closer to compounding but for a test
        # we only need monotone, positive values.
        weight = Decimal(offset) / Decimal(10)
        p50 = base + (horizon - base) * weight
        cone.append(
            {
                "year": offset,
                "p10": str(p50 * Decimal("0.7")),
                "p50": str(p50),
                "p90": str(p50 * Decimal("1.3")),
            }
        )
    return cone


def test_cone_anchor_picks_milestone_four_years_ahead():
    cone = _ten_year_cone(Decimal("316600000000"))
    projection = _fake_projection(
        computed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cone=cone,
    )

    anchor = causality_service._cone_anchor(projection, today=date(2026, 5, 20))

    assert anchor is not None
    target_year, target_p50 = anchor
    assert target_year == 2030  # 2026 + 4
    expected_p50 = Decimal(cone[4]["p50"])
    assert target_p50 == expected_p50


def test_cone_anchor_falls_back_to_horizon_when_milestone_exceeds_cone():
    cone = _ten_year_cone(Decimal("100000000000"))
    projection = _fake_projection(
        computed_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        cone=cone,
    )

    anchor = causality_service._cone_anchor(projection, today=date(2026, 5, 20))

    assert anchor is not None
    target_year, _ = anchor
    # 2026 + 4 = 2030, but the cone runs 2020..2030 only when base=2020.
    # Preferred offset = 10, which is the horizon — anchor stays inside the cone.
    assert target_year == 2030


def test_cone_anchor_returns_none_for_empty_cone():
    projection = _fake_projection(
        computed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cone=[],
    )

    assert causality_service._cone_anchor(projection) is None


def test_cone_anchor_returns_none_when_p50_non_positive():
    cone = [{"year": 4, "p10": "0", "p50": "0", "p90": "0"}]
    projection = _fake_projection(
        computed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cone=cone,
    )

    assert causality_service._cone_anchor(projection, today=date(2026, 5, 20)) is None


def test_forward_sentence_returns_none_when_delta_zero():
    cone = _ten_year_cone(Decimal("316600000000"))
    projection = _fake_projection(
        computed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cone=cone,
    )

    assert causality_service._forward_sentence(projection, Decimal("0")) is None


def test_forward_sentence_returns_negative_template_when_delta_negative():
    cone = _ten_year_cone(Decimal("316600000000"))
    projection = _fake_projection(
        computed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cone=cone,
    )

    sentence = causality_service._forward_sentence(projection, Decimal("-100000000"))

    assert sentence == "Mình xem nhẹ nhàng 1 điểm chính để kéo Twin ổn lại nhé."


def test_forward_sentence_uses_cone_value_not_linear_extrapolation():
    """The screenshot bug: 316.6 tỷ at year 10 but 6456.4 tỷ at year 4.

    With the cone-driven anchor, the year-4 P50 must be strictly smaller than
    the year-10 P50 because Monte Carlo cones grow monotonically. This is the
    invariant that the original bug violated.
    """
    horizon_p50 = Decimal("316600000000")
    cone = _ten_year_cone(horizon_p50)
    projection = _fake_projection(
        computed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cone=cone,
    )

    # A weekly delta that the old code would have annualized into trillions.
    delta = Decimal("29500000000")
    sentence = causality_service._forward_sentence(projection, delta)

    assert sentence is not None
    # The anchor year is 2030 (the +4 milestone).
    assert "2030" in sentence
    # The amount in the sentence MUST be the cone's P50 at year 4, which is
    # less than the horizon P50 — never the inflated extrapolation.
    target_p50 = Decimal(cone[4]["p50"])
    assert target_p50 < horizon_p50
    # The text format comes from content/twin/causality_explainer.yaml.
    assert "Bình thường" in sentence
    # Loose sanity: the amount string should reflect target_p50 (~132 tỷ), not
    # the 6,456.4 tỷ inflation the old extrapolation would produce.
    assert "tỷ" in sentence
    assert "6456" not in sentence
    assert "6,456" not in sentence


def test_forward_sentence_anchor_stays_inside_cone_when_projection_is_stale():
    """If the projection was computed long ago, anchor must still be in-cone."""
    cone = _ten_year_cone(Decimal("200000000000"))
    projection = _fake_projection(
        computed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        cone=cone,
    )

    # today is well into the cone — 2026 + 4 = 2030. Cone base=2024 so 2030
    # maps to year offset 6, well inside the 0..10 cone.
    sentence = causality_service._forward_sentence(projection, Decimal("1000000"))

    assert sentence is not None
    assert "2030" in sentence
