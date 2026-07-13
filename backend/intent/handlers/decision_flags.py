"""Feature flags for Phase 4.5 Decision Engine + Phase 4.7 Guardian surfaces.

These helpers are read at the handler / API-router / worker edge only — never
inside a service (layer contract §"Service NEVER reads env"). Each Decision
Engine capability ships dark so the operator can flip it on per-surface once
validated in prod. Same pattern as ``onboarding_v2.is_v2_enabled``.

Kill-switch note (Phase 4.7 §8, ``SCAM_CHECK_ENABLED``): the flag is read at the
handler edge on every request, but ``os.environ`` only changes on process
restart. To disable a Guardian surface in <24h *without* a code deploy, the
operator sets the env var and restarts the service (``scripts/rebuild-finance-prod.sh``
/ launchd reload) — see the §8 runbook in ``phase-4.7-detailed.md``. A
DB/config runtime toggle is deferred to a later phase unless §8 one-strike
demands instant-off.
"""

from __future__ import annotations

import os

_TRUTHY = ("1", "true", "yes", "on")
_FALSY = ("0", "false", "no", "off")


def _enabled(env: str, *, default: bool) -> bool:
    raw = os.environ.get(env, "true" if default else "false").lower()
    return raw not in _FALSY if default else raw in _TRUTHY


CLARITY_METER_ENABLED_ENV = "CLARITY_METER_ENABLED"


def is_clarity_meter_enabled() -> bool:
    """Độ Nét meter (E3). OFF by default — when dark, every surface renders
    exactly as it did before Phase 4.5."""
    return _enabled(CLARITY_METER_ENABLED_ENV, default=False)


PLAN_FEASIBILITY_QA_ENABLED_ENV = "PLAN_FEASIBILITY_QA_ENABLED"


def is_plan_feasibility_qa_enabled() -> bool:
    """Plan-to-goal feasibility Q&A (E2). OFF by default — when dark, a
    "có khả thi không?" question falls back to the generic advisory handler,
    so the surface behaves exactly as it did before Phase 4.5."""
    return _enabled(PLAN_FEASIBILITY_QA_ENABLED_ENV, default=False)


SHOCK_SIMULATION_ENABLED_ENV = "SHOCK_SIMULATION_ENABLED"


def is_shock_simulation_enabled() -> bool:
    """Shock simulation + liquidation advice (E1). OFF by default — when dark, a
    "nếu phải chi X thì sao?" question falls back to the generic advisory
    handler, so the surface behaves exactly as it did before Phase 4.5."""
    return _enabled(SHOCK_SIMULATION_ENABLED_ENV, default=False)


EXPORT_EXCEL_ENABLED_ENV = "EXPORT_EXCEL_ENABLED"


def is_export_excel_enabled() -> bool:
    """Excel export (E4 #4.1). **ON by default** — data portability is a
    baseline promise, not an experiment. Flip to ``false`` only to kill the
    ``/export`` command / menu button in an incident (e.g. a Telegram
    upload outage)."""
    return _enabled(EXPORT_EXCEL_ENABLED_ENV, default=True)


TONE_DIAL_ENABLED_ENV = "TONE_DIAL_ENABLED"


def is_tone_dial_enabled() -> bool:
    """Tone dial — gentle/strict preference (E4 #4.2). OFF by default: when
    dark the /profile tone control is hidden and every surface renders in the
    default gentle voice, exactly as before Phase 4.5."""
    return _enabled(TONE_DIAL_ENABLED_ENV, default=False)


ACTIVATION_NUDGE_ENABLED_ENV = "ACTIVATION_NUDGE_ENABLED"


def is_activation_nudge_enabled() -> bool:
    """Activation nudge — first-message-tự-nổ for never-activated users
    (Phase 4.6 E2). OFF by default — opt-in experiment. When dark the hourly
    job skips the ``never_activated`` empathy trigger AND the worker skips the
    ``activation_first_reply`` funnel stamp, so behaviour is byte-identical to
    pre-4.6. Read at the job / worker edge only (layer contract)."""
    return _enabled(ACTIVATION_NUDGE_ENABLED_ENV, default=False)


DRIFT_WARNING_ENABLED_ENV = "DRIFT_WARNING_ENABLED"


def is_drift_warning_enabled() -> bool:
    """Drift / overspend warnings — Phase 4.7 Epic 1. OFF by default (gated on
    the G1 decision-adoption gate + owner sign-off). When dark the hourly
    empathy job skips the ``spending_drift`` trigger while every pre-existing
    empathy trigger still fires, so behaviour is byte-identical to pre-4.7.
    Read at the job edge only — the empathy engine never reads env (layer
    contract)."""
    return _enabled(DRIFT_WARNING_ENABLED_ENV, default=False)


SCAM_CHECK_ENABLED_ENV = "SCAM_CHECK_ENABLED"


def is_scam_check_enabled() -> bool:
    """Scam check v1 — Phase 4.7 Epic 2 (red line). OFF by default; flip is
    gated on legal sign-off of the red-flags wording + disclaimer. When dark a
    "kèo này có nên không?" question delegates to the generic advisory handler
    (byte-identical pre-4.7), never ``out_of_scope``.

    This flag is the §8 kill switch: on a harmful-output report the operator
    sets ``SCAM_CHECK_ENABLED=false`` and restarts the service to take the
    surface offline in <24h without a code deploy (see module docstring +
    ``phase-4.7-detailed.md`` §8 runbook). Read at the handler edge only."""
    return _enabled(SCAM_CHECK_ENABLED_ENV, default=False)
