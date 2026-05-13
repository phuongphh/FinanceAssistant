from decimal import Decimal

from backend.models.onboarding_session import SEGMENT_MASS_AFFLUENT, SEGMENT_STARTER
from backend.services.onboarding import data_quality_service


def test_amount_warning_low_and_high_guardrails():
    low = data_quality_service.amount_warning(Decimal("500"), segment=SEGMENT_STARTER)
    high = data_quality_service.amount_warning(Decimal("100000000001"), segment=SEGMENT_MASS_AFFLUENT)

    assert low is not None
    assert low.warning_type == data_quality_service.WARNING_LOW_AMOUNT
    assert high is not None
    assert high.warning_type == data_quality_service.WARNING_HIGH_AMOUNT


def test_currency_warning_only_for_non_starter_segments():
    starter = data_quality_service.amount_warning(Decimal("5000000"), segment=SEGMENT_STARTER)
    affluent = data_quality_service.amount_warning(Decimal("5000000"), segment=SEGMENT_MASS_AFFLUENT)

    assert starter is None
    assert affluent is not None
    assert affluent.warning_type == data_quality_service.WARNING_CURRENCY_AMBIGUOUS


def test_estimate_options_offer_three_distinct_positive_choices():
    options = data_quality_service.estimate_options(Decimal("500"))
    values = [value for _, value in options]

    assert len(values) == 3
    assert values == [Decimal("500"), Decimal("500000"), Decimal("500000000")]
