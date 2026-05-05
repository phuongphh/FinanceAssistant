# Phase 3.6 — Retrospective

> **Story:** [P3.6-S13 / #173](../issues/active/issue-173.md)
> **Phase span:** approx 1.5 weeks (May 4 — May 5, 2026)
> **Status:** Phase complete; this doc is the post-mortem.

This is the lookback for Phase 3.6 — the menu UX revamp that turned
the V1 flat 8-button menu (with deprecated "Quét Gmail" buttons) into
a wealth-adaptive 3-level hierarchy matching the Personal CFO
positioning. Written so future contributors can build on what worked
and avoid the rough edges.

---

## 1. What Worked Well

### Reading `users.wealth_level` instead of recomputing
The phase doc proposed calling ``NetWorthCalculator`` on every menu
render plus a 5-min in-memory cache. We instead read the
``users.wealth_level`` column the asset wizard already keeps fresh
via ``ladder.update_user_level``. This delivered:

- **Zero new DB queries** on the menu hot path — the user row is
  already loaded for callback dispatch.
- **No new caching layer** to maintain or test for staleness.
- **Atomic with real life events.** Wealth tier moves only when
  the user adds/edits assets; transient market noise (a stock dip
  pushing 200 → 199 tỷ) doesn't flip-flop the menu copy.

Worth replicating: when a downstream system already keeps the value
fresh, *use it*. Don't recompute defensively.

### YAML-driven content + Python-driven action map
Splitting `content/menu_copy.yaml` (what the user sees) from
`menu_handler._INTENT_MAP / _DIRECT_HANDLERS / _ADVISORY_MAP` (what
each action does) kept Epic 1 small (~600 lines of new code for the
entire 5-category × 22-action surface). Copy team can tweak YAML
without touching Python; engineers can add an action without
re-reading the entire menu copy.

### Synthesised IntentResult to reuse Phase 3.5 dispatcher
The menu's "📊 Tổng tài sản" button doesn't reimplement the asset
listing — it builds an ``IntentResult(intent=QUERY_ASSETS,
confidence=1.0)`` and hands it to the existing dispatcher. Same
personality wrapper, same follow-up keyboard, same analytics as the
free-form path. One source of truth across menu and NL.

### Hard cutover with graceful redirect
Epic 3 owns 100% of the ``menu:*`` namespace. New callbacks render
the V2 UX; legacy V1 callbacks (``menu:gmail_scan``,
``menu:report``, etc.) get a friendly "menu has been upgraded, type
/menu" redirect. Stale chat-history bubbles from before deploy stay
useful instead of bricking. The redirect is dead code in ~1 month;
removal tracked as follow-up.

### Auto-syncing phase-status.yaml
``scripts/sync_phase_status.py`` updated CLAUDE.md, README.md, and
strategy.md from a single YAML edit. Saved manual cross-doc
updates and prevented drift between roadmap mentions.

---

## 2. What Was Harder Than Expected

### V1 callback prefix collision
The V1 flat menu used ``menu:<feature_key>`` callbacks
(``menu:gmail_scan``, ``menu:report``, etc.). The new V2 hierarchy
uses ``menu:<category>`` and ``menu:<category>:<action>`` —
overlapping prefix. Epic 1 worked around this by returning False
from the new handler for unknown second segments, letting the V1
fallback respond. Epic 3 inverted: the new handler now owns the
prefix and explicitly redirects V1 callbacks. Cleaner final state,
but the Epic 1 transitional shape was a wart for two days.

Lesson: when designing a new callback namespace that overlaps with
V1, plan the cutover as part of the design (not "we'll figure it
out in Epic 3"). Could have shipped Epic 1 with the redirect from
day one.

### Test fragility on copy substrings
Initial Epic 2 tests asserted on Vietnamese copy fragments
("Trợ lý CFO cá nhân", "anh/chị") to verify adaptive intros.
Self-review caught these would flake the moment a copywriter
tweaked YAML. Refactored to assert structural properties (YAML-
rendered text appears verbatim, all 4 levels render distinct
copy). Now copy tweaks don't break the test suite.

Worth replicating: when YAML is the source of truth, tests should
load from the same YAML — not hard-code its contents.

### OpenClaw skill compatibility
The V1 ``services/menu_service.py`` still feeds the OpenClaw
``finance-menu`` skill via ``GET /telegram/menu``. We wanted to
delete the file outright but archiving with a deprecation header
was the right call — deleting would have broken OpenClaw without
a migration path. The archived module ships with a clear "delete
when OpenClaw is sunset" note.

---

## 3. What Surprised Us

### How much V1 was already partially deprecated
The V1 menu had buttons for "Quét Gmail" (Phase 3A removed Gmail
integration entirely) and the V1 ``BOT_COMMANDS`` listed 7
commands of which only 4 still made sense post-V2. Phase 3.6
wasn't just "new menu" — it was "menu finally catches up to
where the rest of the codebase already moved to."

### How small the diff was
Epic 1 + 2 + 3 combined: ~1300 lines added, ~50 lines deleted in
production code. The bulk of the work was content (YAML), config
(setup_commands), and tests. The actual handler logic is small
because Phase 3.5's dispatcher does the heavy lifting.

---

## 4. Patterns to Reuse in Future Phases

### Pure formatter + impure call site
``MenuFormatter`` returns ``(text, dict_keyboard)`` tuples with no
DB / network IO. The handler reads ``user.wealth_level`` and
passes it in. Tests for the formatter don't need a database; tests
for the handler can mock just the user lookup. This shape worked
well for the briefing formatter too — adopt it for new UI surfaces
in Phase 3B / 4.

### Smoke test script in repo
``scripts/phase_3_6_smoke_test.py`` runs offline (no Telegram API
calls) and verifies the menu surface is healthy. Add to deploy
runbook — costs nothing per run, catches "did the YAML break?"
class of bugs in seconds. Phase 3B should ship a similar script.

### Hard cutover with graceful fallback
Don't dual-run V1 and V2 forever. Hard cutover with a clearly-
scoped redirect window (1 month here) is cleaner than carrying
two implementations indefinitely. The redirect carries the
upgrade message — users learn about the change without
operations needing to broadcast.

### Auto-sync from a single YAML
``phase-status.yaml`` → CLAUDE.md / README.md / strategy.md is the
right shape for any cross-doc roadmap state. New phases just
append an entry; sync script handles propagation.

---

## 5. Open Questions / Tech Debt

- **Legacy redirect removal.** ``LEGACY_REDIRECT_TEXT`` and the
  redirect branch in ``menu_handler.handle_menu_callback`` are
  intended to be deleted ~1 month post-deploy when stale chat
  bubbles age out. **Follow-up issue: file in early June 2026.**
- **OpenClaw `finance-menu` skill sunset.** The
  ``services/_archived/menu_service_v1.py`` module survives only
  to feed ``GET /telegram/menu`` for OpenClaw. When that skill is
  retired (or migrated to the V2 menu YAML), the entire archived
  module + the HTTP endpoint can go.
- **Add-goal wizard.** ``menu:goals:add`` currently sends a
  free-form prompt because the wizard doesn't exist yet. Phase 4
  should ship the wizard and replace the stub.
- **Edit-asset wizard.** Same shape — ``menu:assets:edit`` shows
  the asset list and a free-form prompt; full inline-edit wizard
  is Phase 4.
- **Wealth-tier flicker on boundary.** A user oscillating around
  a tier boundary (29.9 ↔ 30.1tr) sees different intros each menu
  open. This is by design (tier *should* change as wealth
  changes) but might feel jittery. Phase 4 / 5 behavioural
  engine could add hysteresis if user complaints surface.

---

## 6. Metrics Achieved

| Metric | Target | Actual |
|---|---|---|
| Menu categories | 5 (vs 8 V1) | 5 ✅ |
| Wealth-level intros | 4 distinct bands | 4 ✅ |
| Bot menu button commands | 4 (vs 7 V1) | 4 ✅ |
| Menu render p95 | < 500 ms | TBD post-deploy |
| Edit-in-place latency | < 300 ms | TBD post-deploy |
| Pre-existing test failures | unchanged | 25 → 25 ✅ |
| New tests added | — | 47 (Epic 1: 33, Epic 2: 12, Epic 3: 2) |

---

## 7. Recommendation for Phase 3B

Phase 3B (Market Intelligence) should:

1. **Reuse the menu adaptive pattern.** Market summaries also
   benefit from wealth-level adaptive copy (a Starter wants
   "what is VN-Index", a HNW wants "VN-Index sector rotation
   today"). The same ``user.wealth_level``-driven approach
   applies — no new caching needed.
2. **Wire new actions into the existing menu YAML.** "📊 Thị
   trường" sub-menu has 5 actions; new market features should
   slot in via ``content/menu_copy.yaml`` + ``_INTENT_MAP`` /
   ``_DIRECT_HANDLERS`` rather than new sub-menus. Aim to keep
   the 5-category top level stable through Phase 3B — that's
   the user's mental model now.
3. **Ship a smoke test alongside the deploy.** Pattern from
   ``scripts/phase_3_6_smoke_test.py``: offline import + render,
   no Telegram API. Cheap insurance.
4. **Replace remaining stubs.** The "coming soon" messages in
   ``menu_handler._send_coming_soon`` need to disappear as
   Phase 3B / 4 ship the underlying wizards.

---

**Phase 3.6 was the smallest non-bugfix phase to date (~1.5 weeks
of net work, 3 small PRs) and the cleanest cutover. The scope
discipline — "menu plumbing only, no new business logic" — paid
for itself. Phase 3B should follow the same playbook. 🎨💚**
