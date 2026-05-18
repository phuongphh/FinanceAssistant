"""Twin admin alert thresholds for Phase 4.3 Epic 4.

Kept dependency-free for now; notification dispatch can plug into this module
when the operator notification channel is finalized.
"""
from __future__ import annotations


def evaluate_loop_alerts(loop_close_rate_pct: float, action_completion_pct: float) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    if loop_close_rate_pct < 15:
        alerts.append({"severity": "critical", "message": "Loop close rate < 15% for the selected window."})
    if action_completion_pct < 20:
        alerts.append({"severity": "warning", "message": "Action completion < 20% for the selected window."})
    return alerts


def evaluate_delta_bias_alert(positive_ratio: float) -> list[dict[str, str]]:
    if positive_ratio > 0.8:
        return [{"severity": "warning", "message": ">80% positive deltas — Twin math possibly biased."}]
    return []
