"""Phase 4.1 Epic C — Soft Launch Playbook & Founding Cohort tests.

Covers the deterministic / mockable surface of:

  - C.1 ``scripts/soft_launch_acquisition`` (token generation,
    source distribution, invite-URL builder, CSV writer)
  - C.1 source-aware welcome copy in ``content/onboarding/welcome_v2.yaml``
  - C.4 founding-member service (assign_sequence cap+idempotency,
    compute_discount, mark_invite_redeemed)
  - C.4 founding-welcome YAML completeness
  - D.1 Zalo channel gated by ``ZALO_CHANNEL_ENABLED`` env / setting

DB-backed atomicity (Postgres advisory lock) is integration-level —
verified manually per ``deploy-checklist.md §5``. Here we test the
PYTHON logic that runs inside that lock: re-check, increment, cap
boundary.
"""
from __future__ import annotations

import csv
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml


# ====================================================================
# C.1 — soft_launch_acquisition script (pure functions)
# ====================================================================


def test_script_default_sources_match_phase_spec():
    """Phase 4.1 spec pins the 5 source codes — guard against typos."""
    from scripts.soft_launch_acquisition import SOURCES

    assert SOURCES == (
        "friends",
        "personal_fb",
        "vn_finance_community",
        "direct_msg",
        "tg_finance_groups",
    )


def test_script_distribute_50_invites_evenly_across_5_sources():
    from scripts.soft_launch_acquisition import _distribute_sources

    out = _distribute_sources(50)
    counts: dict[str, int] = {}
    for s in out:
        counts[s] = counts.get(s, 0) + 1
    assert len(out) == 50
    assert set(counts.values()) == {10}, f"expected 10 each, got {counts}"


def test_script_distribute_uneven_count_spreads_remainder_to_first_sources():
    from scripts.soft_launch_acquisition import SOURCES, _distribute_sources

    # 12 invites across 5 sources → 3, 3, 2, 2, 2 with sources[0..1] getting +1.
    out = _distribute_sources(12)
    counts: dict[str, int] = {}
    for s in out:
        counts[s] = counts.get(s, 0) + 1
    assert counts[SOURCES[0]] == 3
    assert counts[SOURCES[1]] == 3
    assert counts[SOURCES[2]] == 2
    assert sum(counts.values()) == 12


def test_script_generate_tokens_are_unique_and_high_entropy():
    from scripts.soft_launch_acquisition import _generate_tokens

    tokens = _generate_tokens(50)
    assert len(tokens) == 50
    assert len(set(tokens)) == 50, "duplicate tokens generated"
    # URL-safe token_urlsafe(16) returns ~22 chars from 16 bytes.
    for t in tokens:
        assert 20 <= len(t) <= 24, f"unexpected token length {len(t)}: {t!r}"
        # Must be URL-safe characters only.
        assert all(c.isalnum() or c in "-_" for c in t), f"non-urlsafe char in {t!r}"


def test_script_invite_url_uses_telegram_deep_link_format():
    from scripts.soft_launch_acquisition import _build_invite_url

    url = _build_invite_url("BeTienBot", "abc123")
    assert url == "https://t.me/BeTienBot?start=invite_abc123"


def test_script_csv_export_has_header_and_one_row_per_invite(tmp_path: Path):
    from scripts.soft_launch_acquisition import GeneratedInvite, _write_csv

    invites = [
        GeneratedInvite(
            token=f"tok{i}",
            source="friends",
            invite_url=f"https://t.me/BeTienBot?start=invite_tok{i}",
        )
        for i in range(3)
    ]
    out_path = tmp_path / "out.csv"
    _write_csv(
        invites,
        output_path=out_path,
        batch_name="test-batch",
        grants_founding=True,
    )

    rows = list(csv.reader(out_path.open(encoding="utf-8")))
    header, *data = rows
    assert header == [
        "sequence",
        "invite_url",
        "source",
        "batch_name",
        "grants_founding_status",
        "generated_at_utc",
    ]
    assert len(data) == 3
    assert data[0][0] == "1"
    assert data[0][1] == "https://t.me/BeTienBot?start=invite_tok0"
    assert data[0][2] == "friends"
    assert data[0][3] == "test-batch"
    assert data[0][4] == "TRUE"


# ====================================================================
# C.1 — source-aware welcome copy YAML
# ====================================================================


def _load_welcome_v2() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[2]
        / "content"
        / "onboarding"
        / "welcome_v2.yaml"
    )
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_welcome_v2_has_variant_for_every_source():
    """Every source in the script must have a copy variant. Missing one
    means a user from that channel gets the generic intro and we lose
    the source-aware framing.
    """
    from scripts.soft_launch_acquisition import SOURCES

    copy = _load_welcome_v2()
    variants = copy.get("source_variants") or {}
    missing = [s for s in SOURCES if s not in variants]
    assert not missing, f"welcome_v2.yaml missing source_variants for: {missing}"
    for src, body in variants.items():
        assert "prefix" in body, f"source_variants.{src} has no prefix"
        assert body["prefix"].strip(), f"source_variants.{src}.prefix is empty"


def test_welcome_v2_goal_acks_cover_three_goals():
    copy = _load_welcome_v2()
    acks = copy["step_1_goal"]["goal_acks"]
    assert set(acks.keys()) == {"understand_wealth", "plan_goal", "track_spending"}
    for goal, msg in acks.items():
        assert msg.strip(), f"goal_acks.{goal} is empty"


def test_welcome_v2_demo_banner_has_explicit_framing():
    """A.1 demo mode framing must include the word 'demo' AND tell
    user this is NOT their Twin — both required to avoid loss-of-trust."""
    copy = _load_welcome_v2()
    body = copy["demo_banner"]["body"].lower()
    assert "demo" in body
    # Phrasing must convey 'this is not yours yet' — Twin of bạn (you) must appear.
    assert "twin của bạn" in body


# ====================================================================
# C.4 — founding-welcome YAML completeness
# ====================================================================


def _load_founding_welcome() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[2]
        / "content"
        / "onboarding"
        / "founding_welcome.yaml"
    )
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_founding_welcome_yaml_has_banner_with_sequence_placeholder():
    copy = _load_founding_welcome()
    banner = copy["banner"]
    # The banner MUST reference both the sequence (#N) and the promise.
    assert "{sequence}" in banner, "banner missing {sequence} placeholder"
    assert "Founding Member" in banner
    assert "44.000đ" in banner and "88.000đ" in banner, "promise pricing missing"
    assert "50%" in banner or "giảm 50%" in banner.lower(), "discount promise missing"


def test_founding_welcome_cap_reached_present():
    copy = _load_founding_welcome()
    cap = copy["cap_reached"]
    assert cap.strip(), "cap_reached copy is empty"
    # Must still be warm — Phase 4.1 risk #5: cap-reached user must not feel rejected.
    assert "miễn phí" in cap, "cap_reached should explicitly mention free access"


def test_founding_welcome_whoami_template_renders():
    """Whoami template must accept the documented format keys without
    KeyError, including the optional founding_line."""
    copy = _load_founding_welcome()
    rendered = copy["whoami_template"].format(
        display_name="Linh",
        segment="young_pro",
        onboarded_at="12/05/2026",
        days_active=3,
        founding_line=copy["founding_line_template"].format(
            sequence=7, founding_date="12/05/2026"
        ),
    )
    assert "Linh" in rendered
    assert "young_pro" in rendered
    assert "#7" in rendered  # founding sequence shown


# ====================================================================
# C.4 — compute_discount (pure)
# ====================================================================


def test_compute_discount_is_50pct_for_founding():
    from backend.services.founding.founding_member_service import compute_discount

    founding = SimpleNamespace(is_founding_member=True)
    assert compute_discount(founding) == Decimal("0.5")


def test_compute_discount_is_zero_for_non_founding():
    from backend.services.founding.founding_member_service import compute_discount

    non = SimpleNamespace(is_founding_member=False)
    assert compute_discount(non) == Decimal("0")


# ====================================================================
# C.4 — assign_sequence logic via FakeDB
# ====================================================================


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


class _FakeFoundingDB:
    """Minimal AsyncSession stand-in for the assign_sequence flow.

    Tracks the advisory-lock call, the max-sequence query, and a flush.
    The advisory lock is a side-effect (Postgres-level), so locally we
    just record it was called.
    """

    def __init__(self, *, max_sequence: int | None):
        self._max_sequence = max_sequence
        self.advisory_lock_calls = 0
        self.flush_count = 0
        # ``get`` returns the user we hold a reference to — caller sets it.
        self._user_after_lock: Any = None

    def set_user_after_lock(self, user: Any) -> None:
        self._user_after_lock = user

    async def execute(self, stmt):  # noqa: ANN001
        text_form = str(stmt).lower()
        if "pg_advisory" in text_form:
            self.advisory_lock_calls += 1
            return _FakeScalarResult(None)
        if "max" in text_form:
            return _FakeScalarResult(self._max_sequence)
        return _FakeScalarResult(None)

    async def get(self, model, pk):  # noqa: ANN001
        return self._user_after_lock

    async def flush(self):
        self.flush_count += 1


def _make_user(seq: int | None = None, founding: bool | None = None) -> SimpleNamespace:
    is_founding = founding if founding is not None else (seq is not None)
    return SimpleNamespace(
        id=uuid.uuid4(),
        is_founding_member=is_founding,
        founding_member_sequence=seq,
        founding_member_at=None,
        acquisition_source=None,
        display_name="Tester",
    )


@pytest.mark.asyncio
async def test_assign_sequence_idempotent_for_existing_founding_user():
    """Re-assigning an already-promoted user returns the stored seq —
    no advisory lock, no flush, no increment."""
    from backend.services.founding import founding_member_service

    user = _make_user(seq=7)
    db = _FakeFoundingDB(max_sequence=10)

    result = await founding_member_service.assign_sequence(db, user)

    assert result.sequence == 7
    assert db.advisory_lock_calls == 0
    assert db.flush_count == 0


@pytest.mark.asyncio
async def test_assign_sequence_grants_next_when_seats_available():
    from backend.services.founding import founding_member_service

    user = _make_user(seq=None, founding=False)
    db = _FakeFoundingDB(max_sequence=4)
    db.set_user_after_lock(user)  # re-check inside lock returns same row

    result = await founding_member_service.assign_sequence(db, user)

    assert result.sequence == 5  # 4 + 1
    assert user.is_founding_member is True
    assert user.founding_member_sequence == 5
    assert user.founding_member_at is not None
    assert db.advisory_lock_calls == 1
    assert db.flush_count == 1


@pytest.mark.asyncio
async def test_assign_sequence_grants_seat_one_when_cohort_empty():
    from backend.services.founding import founding_member_service

    user = _make_user(seq=None, founding=False)
    db = _FakeFoundingDB(max_sequence=None)
    db.set_user_after_lock(user)

    result = await founding_member_service.assign_sequence(db, user)
    assert result.sequence == 1
    assert user.founding_member_sequence == 1


@pytest.mark.asyncio
async def test_assign_sequence_raises_when_cap_reached():
    from backend.services.founding.founding_member_service import (
        FOUNDING_COHORT_CAP,
        FoundingCapReachedError,
        assign_sequence,
    )

    user = _make_user(seq=None, founding=False)
    db = _FakeFoundingDB(max_sequence=FOUNDING_COHORT_CAP)
    db.set_user_after_lock(user)

    with pytest.raises(FoundingCapReachedError):
        await assign_sequence(db, user)
    # User must NOT be promoted on cap-reached — the cap_reached copy
    # explicitly tells them they're still welcome but not founding.
    assert user.is_founding_member is False
    assert user.founding_member_sequence is None


@pytest.mark.asyncio
async def test_assign_sequence_recheck_inside_lock_returns_stored_seq():
    """Race-condition guard: between the initial caller check and the
    advisory lock, another tx may have promoted this user. The re-check
    inside the lock must find the now-set sequence and return it.
    """
    from backend.services.founding import founding_member_service

    # Outer view: user not promoted.
    user = _make_user(seq=None, founding=False)
    db = _FakeFoundingDB(max_sequence=99)
    # Inner view (after lock): some other tx already wrote sequence 12.
    promoted = _make_user(seq=12)
    db.set_user_after_lock(promoted)

    result = await founding_member_service.assign_sequence(db, user)

    # We honor the inner-tx assignment; outer user object stays untouched.
    assert result.sequence == 12
    assert db.advisory_lock_calls == 1
    # No flush because we did not write — the other tx already did.
    assert db.flush_count == 0


# ====================================================================
# C.1 — mark_invite_redeemed sets acquisition_source idempotently
# ====================================================================


@pytest.mark.asyncio
async def test_mark_invite_redeemed_stamps_user_and_invite():
    from backend.services.founding import founding_member_service

    user = _make_user(seq=None, founding=False)
    invite = SimpleNamespace(
        token="tok-1",
        source="vn_finance_community",
        redeemed_by_user_id=None,
        redeemed_at=None,
    )
    db = _FakeFoundingDB(max_sequence=None)

    await founding_member_service.mark_invite_redeemed(db, invite, user)

    assert invite.redeemed_by_user_id == user.id
    assert invite.redeemed_at is not None
    assert user.acquisition_source == "vn_finance_community"
    assert db.flush_count == 1


@pytest.mark.asyncio
async def test_mark_invite_redeemed_preserves_prior_acquisition_source():
    """If the user already has a source (e.g., they linked from a non-invite
    channel first), the invite redemption must NOT clobber it — attribution
    integrity matters for cohort analysis.
    """
    from backend.services.founding import founding_member_service

    user = _make_user(seq=None, founding=False)
    user.acquisition_source = "direct_msg"
    invite = SimpleNamespace(
        token="tok-1",
        source="friends",
        redeemed_by_user_id=None,
        redeemed_at=None,
    )
    db = _FakeFoundingDB(max_sequence=None)

    await founding_member_service.mark_invite_redeemed(db, invite, user)

    assert invite.source == "friends"
    assert user.acquisition_source == "direct_msg"


# ====================================================================
# Token-free founding — record_source (src_<source> deep-link path)
# ====================================================================


def test_founding_sources_is_canonical_for_script():
    """The script re-exports the service tuple — they must be identical so
    the onboarding handler validates ``src_<source>`` against the same set
    the distribution script round-robins over."""
    from backend.services.founding.founding_member_service import FOUNDING_SOURCES
    from scripts.soft_launch_acquisition import SOURCES

    assert SOURCES is FOUNDING_SOURCES
    assert FOUNDING_SOURCES == (
        "friends",
        "personal_fb",
        "vn_finance_community",
        "direct_msg",
        "tg_finance_groups",
    )


@pytest.mark.asyncio
async def test_record_source_sets_known_source():
    from backend.services.founding import founding_member_service

    user = _make_user(seq=None, founding=False)
    db = _FakeFoundingDB(max_sequence=None)

    await founding_member_service.record_source(db, user, "tg_finance_groups")

    assert user.acquisition_source == "tg_finance_groups"
    assert db.flush_count == 1


@pytest.mark.asyncio
async def test_record_source_ignores_unknown_source():
    """A bogus ``src_<x>`` payload (typo / tampering) must not write a
    junk source — only the 5 known channels are accepted."""
    from backend.services.founding import founding_member_service

    user = _make_user(seq=None, founding=False)
    db = _FakeFoundingDB(max_sequence=None)

    await founding_member_service.record_source(db, user, "spam_channel")

    assert user.acquisition_source is None
    assert db.flush_count == 0


@pytest.mark.asyncio
async def test_record_source_ignores_none():
    """Bare /start (no payload) carries no source — nothing to record."""
    from backend.services.founding import founding_member_service

    user = _make_user(seq=None, founding=False)
    db = _FakeFoundingDB(max_sequence=None)

    await founding_member_service.record_source(db, user, None)

    assert user.acquisition_source is None
    assert db.flush_count == 0


@pytest.mark.asyncio
async def test_record_source_preserves_prior_source():
    """First touch wins — a later src_ link must not overwrite the
    channel that originally converted the user."""
    from backend.services.founding import founding_member_service

    user = _make_user(seq=None, founding=False)
    user.acquisition_source = "friends"
    db = _FakeFoundingDB(max_sequence=None)

    await founding_member_service.record_source(db, user, "personal_fb")

    assert user.acquisition_source == "friends"
    assert db.flush_count == 0


# ====================================================================
# _claim_founding — token-free orchestration in onboarding_v2 handler
# ====================================================================


def _patch_claim_deps(monkeypatch, *, assignment=None, cap=False):
    """Patch the handler collaborators so _claim_founding runs in isolation.

    Returns a list that records analytics.track calls.
    """
    from backend.bot.handlers import onboarding_v2
    from backend.services.founding import founding_member_service

    monkeypatch.setattr(
        onboarding_v2.onboarding_service,
        "load_copy",
        lambda: {
            "source_variants": {
                "friends": {"prefix": "PREFIX_FRIENDS"},
            }
        },
    )
    monkeypatch.setattr(
        onboarding_v2, "_load_founding_copy", lambda: {"banner": "BANNER #{sequence}"}
    )

    async def _fake_assign(db, user):  # noqa: ANN001
        if cap:
            from backend.services.founding.founding_member_service import (
                FoundingCapReachedError,
            )

            raise FoundingCapReachedError()
        user.is_founding_member = True
        user.founding_member_sequence = assignment.sequence
        return assignment

    monkeypatch.setattr(founding_member_service, "assign_sequence", _fake_assign)

    tracked: list[dict] = []
    monkeypatch.setattr(
        onboarding_v2.analytics,
        "track",
        lambda event, **kw: tracked.append({"event": event, **kw}),
    )
    return tracked


@pytest.mark.asyncio
async def test_claim_founding_grants_seat_with_source_prefix(monkeypatch):
    from types import SimpleNamespace

    from backend.bot.handlers import onboarding_v2

    assignment = SimpleNamespace(sequence=3)
    tracked = _patch_claim_deps(monkeypatch, assignment=assignment)

    user = _make_user(seq=None, founding=False)
    db = _FakeFoundingDB(max_sequence=None)

    text = await onboarding_v2._claim_founding(db, user, "friends")

    assert user.acquisition_source == "friends"
    assert "PREFIX_FRIENDS" in text
    assert "BANNER #3" in text
    assert tracked and tracked[0]["event"] == "founding_member_activated"
    assert tracked[0]["properties"]["source"] == "friends"


@pytest.mark.asyncio
async def test_claim_founding_bare_start_grants_seat_without_prefix(monkeypatch):
    """No payload → no source prefix, but still a founding seat + banner."""
    from types import SimpleNamespace

    from backend.bot.handlers import onboarding_v2

    assignment = SimpleNamespace(sequence=1)
    tracked = _patch_claim_deps(monkeypatch, assignment=assignment)

    user = _make_user(seq=None, founding=False)
    db = _FakeFoundingDB(max_sequence=None)

    text = await onboarding_v2._claim_founding(db, user, None)

    assert user.acquisition_source is None
    assert text == "BANNER #1"
    assert tracked[0]["properties"]["source"] is None


@pytest.mark.asyncio
async def test_claim_founding_cap_reached_shows_prefix_only_no_banner(monkeypatch):
    from backend.bot.handlers import onboarding_v2

    tracked = _patch_claim_deps(monkeypatch, cap=True)

    user = _make_user(seq=None, founding=False)
    db = _FakeFoundingDB(max_sequence=None)

    text = await onboarding_v2._claim_founding(db, user, "friends")

    # Source still attributed; banner suppressed (organic user past cap).
    assert user.acquisition_source == "friends"
    assert text == "PREFIX_FRIENDS"
    assert tracked == []


@pytest.mark.asyncio
async def test_claim_founding_cap_reached_bare_start_returns_none(monkeypatch):
    from backend.bot.handlers import onboarding_v2

    _patch_claim_deps(monkeypatch, cap=True)

    user = _make_user(seq=None, founding=False)
    db = _FakeFoundingDB(max_sequence=None)

    text = await onboarding_v2._claim_founding(db, user, None)

    assert text is None


@pytest.mark.asyncio
async def test_claim_founding_returning_member_no_duplicate_banner(monkeypatch):
    """A user who already holds a sequence re-running /start must not get a
    second banner or a duplicate analytics event."""
    from types import SimpleNamespace

    from backend.bot.handlers import onboarding_v2

    assignment = SimpleNamespace(sequence=5)
    tracked = _patch_claim_deps(monkeypatch, assignment=assignment)

    user = _make_user(seq=5)  # already founding
    db = _FakeFoundingDB(max_sequence=None)

    text = await onboarding_v2._claim_founding(db, user, "friends")

    assert text == "PREFIX_FRIENDS"  # prefix only, no banner
    assert tracked == []


# ====================================================================
# D.1 — Zalo channel feature flag
# ====================================================================


def test_zalo_channel_default_off_in_settings_class():
    """Reading the Settings class default (not the cached instance, to
    avoid env-var pollution) must show ``zalo_channel_enabled = False``.
    The whole soft-launch channel discipline rides on this default.
    """
    from backend.config import Settings

    default = Settings.model_fields["zalo_channel_enabled"].default
    assert default is False, (
        "ZALO_CHANNEL_ENABLED default must be False for Phase 4.1 — "
        "soft launch is Telegram-only."
    )


def test_main_module_gates_zalo_router_on_setting(monkeypatch):
    """Static-source check: the Zalo router include in ``backend/main.py``
    must be guarded by ``settings.zalo_channel_enabled``. Catches a
    refactor that silently re-enables the channel.
    """
    main_py = (
        Path(__file__).resolve().parents[2] / "backend" / "main.py"
    ).read_text(encoding="utf-8")
    assert "zalo_channel_enabled" in main_py, (
        "backend/main.py does not reference zalo_channel_enabled — "
        "the Zalo router include is not gated."
    )
    # The gate must precede the zalo_router include — order matters.
    gate_idx = main_py.find("zalo_channel_enabled")
    include_idx = main_py.find("zalo_router.router")
    assert gate_idx != -1 and include_idx != -1
    assert gate_idx < include_idx, (
        "zalo_channel_enabled check must come BEFORE zalo_router include."
    )
