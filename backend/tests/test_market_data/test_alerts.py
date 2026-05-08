from __future__ import annotations

from decimal import Decimal

from backend.market_data.analytics.alerts import format_alert_message, severity_for_change


def test_severity_for_change_thresholds():
    assert severity_for_change(Decimal("5.0")) == "info"
    assert severity_for_change(Decimal("7.0")) == "warning"
    assert severity_for_change(Decimal("10.1")) == "critical"


def test_alert_message_uses_vietnamese_persona():
    message = format_alert_message("HPG", Decimal("6.5"), Decimal("30000"), "info")

    assert "Bé Tiền" in message
    assert "HPG" in message
    assert "tăng" in message
