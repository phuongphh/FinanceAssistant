# Phase 4.7 — Test Cases

<!-- testing-signoff: need to be signed -->
<!--
  Sign-off marker — driven by scripts/archive_phase.py.
  When testing is complete, change "need to be signed" → "signed" on the
  line above. The next archive-phase workflow run will move every
  phase-X-* doc (except the detailed_doc) into docs/archive/.
-->

## Automated regression suite

Run:

```bash
PYTHONPATH=. pytest -q tests/test_phase_4_7 tests/test_menu_twin_navigation.py
```

The suite must cover:

1. Drift baseline uses the previous three complete months and excludes transfers.
2. Both percentage and absolute thresholds must pass before a warning fires.
3. Fewer than three months of history, no goal, cooldown, and disabled flag do not fire.
4. Twin consequence and tone variants render without forbidden blame language.
5. The `menu:twin` callback always produces a visible Twin submenu.

## Manual release checks

1. Open `/menu`, tap **🔮 Twin**, and confirm a new **BÉ TIỀN TƯƠNG LAI** message appears.
2. Tap **📈 Lộ trình**, **⚖️ So tối ưu**, **🌱 Kế hoạch cuộc đời**, **📱 Mini App**, and **❓ Cách hoạt động** once each.
3. Repeat step 1 from an old menu message and after sharing a Twin image.
4. Keep `DRIFT_WARNING_ENABLED=false` until the G1 product gate is approved.

## Phase-exit gaps

Phase 4.7 is not fully releasable while Epic E2 (scam check), legal wording approval,
and its no-verdict/kill-switch tests remain incomplete. Do not mark the phase done
only because the E1/E3 dark-launch tests pass.
