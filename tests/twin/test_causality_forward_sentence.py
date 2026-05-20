"""Regression tests for the Twin causality forward sentence.

The original `_forward_sentence` linearly extrapolated `delta * 52 * years` on
top of the 10-year P50, which produced absurd numbers (e.g. claiming the user
would hit 6456.4 tỷ in 2030 while the main Twin view said 316.6 tỷ in 2036).
The fix reads the forward anchor directly from the Twin cone and pins it to
the same fixed milestone calendar (2027/2030/2035) twin_api_service uses, so
the causality message never disagrees with the main view.

All tests inject ``today=`` explicitly so the suite is wall-clock independent.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from backend.twin.services import causality_service

_TODAY_2026 = date(2026, 5, 20)


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


def test_select_forward_milestone_picks_2030_for_2026_through_2028():
    # 2030 is closest to today+4 from {2027, 2030, 2035}, so the anchor stays
    # parked on 2030 through 2026/2027/2028 — no drift off the milestone grid.
    assert causality_service._select_forward_milestone(2026) == 2030
    assert causality_service._select_forward_milestone(2027) == 2030
    assert causality_service._select_forward_milestone(2028) == 2030


def test_select_forward_milestone_advances_to_2035_when_2030_is_too_close():
    # In 2029, today+4=2033: closer to 2035 (diff 2) than 2030 (diff 3).
    assert causality_service._select_forward_milestone(2029) == 2035
    assert causality_service._select_forward_milestone(2031) == 2035


def test_select_forward_milestone_returns_none_when_all_past():
    assert causality_service._select_forward_milestone(2040) is None


def test_cone_anchor_picks_fixed_milestone_year_2030():
    cone = _ten_year_cone(Decimal("316600000000"))
    projection = _fake_projection(
        computed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cone=cone,
    )

    anchor = causality_service._cone_anchor(projection, today=_TODAY_2026)

    assert anchor is not None
    target_year, target_p50 = anchor
    assert target_year == 2030  # fixed milestone, not 2026+4
    expected_p50 = Decimal(cone[4]["p50"])
    assert target_p50 == expected_p50


def test_cone_anchor_stays_on_2030_in_january_2027():
    # Critical regression: the previous sliding-window logic would have moved
    # the anchor to 2031 here, drifting off the milestone calendar.
    cone = _ten_year_cone(Decimal("316600000000"))
    projection = _fake_projection(
        computed_at=datetime(2027, 1, 5, tzinfo=timezone.utc),
        cone=cone,
    )

    anchor = causality_service._cone_anchor(projection, today=date(2027, 1, 5))

    assert anchor is not None
    target_year, _ = anchor
    assert target_year == 2030


def test_cone_anchor_falls_back_to_horizon_when_milestone_exceeds_cone():
    # Cone with only 3-year horizon: milestone 2030 falls outside, fallback to
    # the cone's actual horizon year (2024 + 3 = 2027).
    short_cone = [
        {"year": offset, "p10": "0", "p50": str(10 * (offset + 1)), "p90": "0"}
        for offset in range(4)
    ]
    projection = _fake_projection(
        computed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        cone=short_cone,
    )

    anchor = causality_service._cone_anchor(projection, today=_TODAY_2026)

    assert anchor is not None
    target_year, _ = anchor
    assert target_year == 2027  # horizon = base + max_offset


def test_cone_anchor_returns_none_for_empty_cone():
    projection = _fake_projection(
        computed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cone=[],
    )

    assert causality_service._cone_anchor(projection, today=_TODAY_2026) is None


def test_cone_anchor_returns_none_when_p50_non_positive():
    cone = [{"year": 4, "p10": "0", "p50": "0", "p90": "0"}]
    projection = _fake_projection(
        computed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cone=cone,
    )

    assert causality_service._cone_anchor(projection, today=_TODAY_2026) is None


def test_forward_sentence_returns_none_when_delta_zero():
    cone = _ten_year_cone(Decimal("316600000000"))
    projection = _fake_projection(
        computed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cone=cone,
    )

    assert (
        causality_service._forward_sentence(
            projection, Decimal("0"), today=_TODAY_2026
        )
        is None
    )


def test_forward_sentence_returns_negative_template_when_delta_negative():
    cone = _ten_year_cone(Decimal("316600000000"))
    projection = _fake_projection(
        computed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cone=cone,
    )

    sentence = causality_service._forward_sentence(
        projection, Decimal("-100000000"), today=_TODAY_2026
    )

    assert sentence == "Mình xem nhẹ nhàng 1 điểm chính để kéo Twin ổn lại nhé."


def test_forward_sentence_uses_cone_value_not_linear_extrapolation():
    """The screenshot bug: 316.6 tỷ at year 10 but 6456.4 tỷ at year 4.

    With the cone-driven anchor, the milestone P50 must be strictly smaller
    than the horizon P50 because Monte Carlo cones grow monotonically. This is
    the invariant the original bug violated.
    """
    horizon_p50 = Decimal("316600000000")
    cone = _ten_year_cone(horizon_p50)
    projection = _fake_projection(
        computed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cone=cone,
    )

    # A weekly delta that the old code would have annualized into trillions.
    delta = Decimal("29500000000")
    sentence = causality_service._forward_sentence(
        projection, delta, today=_TODAY_2026
    )

    assert sentence is not None
    # The anchor year is fixed at 2030 (the medium-term milestone), regardless
    # of which calendar year the test runs in.
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

    # Cone base=2024 so milestone 2030 maps to year offset 6, in-cone.
    sentence = causality_service._forward_sentence(
        projection, Decimal("1000000"), today=_TODAY_2026
    )

    assert sentence is not None
    assert "2030" in sentence


def test_forward_sentence_does_not_drift_with_calendar_year():
    """Anchor stays on a fixed milestone across multiple calendar years."""
    cone = _ten_year_cone(Decimal("316600000000"))
    projection = _fake_projection(
        computed_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        cone=cone,
    )

    s_2026 = causality_service._forward_sentence(
        projection, Decimal("1000000"), today=date(2026, 5, 20)
    )
    s_2027 = causality_service._forward_sentence(
        projection, Decimal("1000000"), today=date(2027, 1, 5)
    )
    s_2028 = causality_service._forward_sentence(
        projection, Decimal("1000000"), today=date(2028, 6, 15)
    )

    # All three sit on the same medium-term milestone — the rest of the Twin
    # surface points to 2030, so causality must too.
    for sentence in (s_2026, s_2027, s_2028):
        assert sentence is not None
        assert "2030" in sentence
        # Hard guard against the old sliding-window output.
        assert "2031" not in sentence
        assert "2032" not in sentence
