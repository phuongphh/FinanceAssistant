# Founding Member Promise

> **Story:** P4.1-C4 (Issue #509).
> **Status:** ACTIVE — promise made at Phase 4.1 soft launch, redeemed
> at Phase 5.7 (Monetization) launch.
> **Owner:** Operator (= founder). Promise survives operator changes —
> see Succession below.

---

## The promise — exact wording shown to users

From `content/onboarding/founding_welcome.yaml` (banner shown at first
`/start invite_<token>`):

> 🌱 **Bạn là Founding Member #N của Bé Tiền** — 1 trong 50 người đầu
> tiên.
>
> Trong giai đoạn này toàn bộ tính năng **miễn phí**.
>
> Khi Bé Tiền Pro ra mắt chính thức (dự kiến cuối 2026), bạn được
> **giảm 50% trọn đời** — 44.000đ/tháng thay vì 88.000đ — để cảm ơn
> sự đồng hành.

This is the contract. Every other detail in this file serves either
clarifying or honoring it.

---

## Who qualifies — exactly

- Any user whose `users.is_founding_member = TRUE` **and**
  `users.founding_member_sequence` is in `[1, 50]`.
- Sequence is assigned **atomically** by
  `backend.services.founding.founding_member_service.assign_sequence`
  inside a Postgres advisory lock (`pg_advisory_xact_lock`). Race
  conditions cannot produce duplicates or skipped numbers within the
  cap.
- The cap is hard-coded as `FOUNDING_COHORT_CAP = 50` in
  `founding_member_service.py`. If we ever raise it, the new range
  gets a different commitment label ("Early Adopter", not "Founding");
  the 50 originals keep their #N badge and price.

## Who does NOT qualify

- Users who `/start` after seat 50 is filled. They see the
  `cap_reached` welcome copy ("Cohort Founding Member 50 chỗ đã đầy,
  nhưng bạn vẫn được dùng tất cả tính năng miễn phí trong giai đoạn
  soft launch.") — no founding flag, no discount.
- Operator + dev test accounts. Test accounts MUST be cleared from
  `invite_codes` and `users` before launch so they don't consume
  seats. The deploy checklist (§5) calls this out.

---

## What "50% lifetime" means in code

At Phase 5.7 the paywall service calls
`founding_member_service.compute_discount(user)`. The current
implementation returns:

- `Decimal("0.5")` if `user.is_founding_member` is `True`
- `Decimal("0")` otherwise

"Lifetime" means: as long as the user keeps an active Pro
subscription, the price stays at 88k × (1 – 0.5) = **44.000đ/tháng**.

- If they pause/cancel and re-subscribe **within 12 months**, the
  discount continues. ("Pause is forgiven once.")
- If they pause for > 12 months OR delete their account, the discount
  is forfeited (handled in Phase 5.7 reactivation flow).
- If we ever change Pro pricing (e.g., 88k → 99k), the discount
  applies to the NEW price, not the old one. The promise is 50% off
  whatever Pro is at the time of charge.

These rules are NOT shown to users in the banner — the banner says
"giảm 50% trọn đời" and we honor it generously. The corner cases above
exist to give the team a clear playbook, not as fine print.

---

## When the promise is redeemed — Phase 5.7 obligations

Phase 4.1 ships the **promise**. Phase 5.7 ships the **payment
infrastructure** that honors it. Phase 5.7's detailed doc MUST include
a checklist item:

- [ ] At Pro paywall first impression, the founding badge appears in
      the pricing block: "Bạn là Founding Member #N — 44.000đ/tháng,
      giảm 50% trọn đời."
- [ ] At checkout, `compute_discount(user)` is called BEFORE any
      promotional codes are applied. The founding discount stacks
      poorly with promos — we don't compound, we always pick the
      better of the two for the user.
- [ ] Receipt email/Telegram message references the discount
      explicitly so the user sees the promise being kept.
- [ ] Operator dashboard has a "Founding cohort active subscriptions"
      counter, separate from the main MRR chart, so we know how many
      of the 50 converted to paid.

Phase 5.7 PR cannot merge without those four boxes ticked.

---

## How we communicate before Phase 5.7 ships

Between soft launch (Phase 4.1) and Pro launch (Phase 5.7), the
following channels MUST surface the promise periodically so it doesn't
fade:

- The **first morning briefing** (Story A.8) doesn't mention pricing
  — it's a wow surface, not a sales surface.
- The `/whoami` command always shows the founding badge for as long
  as the user holds it (rendered from `founding_welcome.yaml`
  `founding_line_template`).
- **One quarterly Telegram message** ("Q-update for Founding Members")
  sent by the operator to all `is_founding_member = TRUE` users. The
  message must include the promise reminder. Operator owns scheduling
  these.

---

## Succession — what happens if the operator changes

The current operator is the founder. If founder steps away:

1. The 50 sequence numbers and the `is_founding_member` flag are
   **stored in the DB**, not in any one person's head. Anyone with
   prod access can query them.
2. The replacement operator inherits the obligation as a condition of
   taking over. This document is the artifact they read on day 1.
3. The promise is **not transferable to the company** (the company can
   change pricing, license, ownership) — it's a personal commitment
   from the team to those 50 humans. A new operator must affirm it in
   writing on day 1 and post the affirmation to the team channel.

If the company is sold or wound down, the 50 users get a 30-day notice
+ data export tool BEFORE any pricing change. This is not legalese —
it's why the promise exists.

---

## Where this is enforced in code

| Concern | Surface |
|---|---|
| Founding flag set atomically | `backend/services/founding/founding_member_service.py::assign_sequence` |
| Cap of 50 | `FOUNDING_COHORT_CAP = 50` constant in same file |
| Banner text | `content/onboarding/founding_welcome.yaml` |
| Discount math | `compute_discount(user)` (same service) |
| User-facing badge | `/whoami` via `backend/bot/handlers/founding_handler.py` |
| Operator view | `/founding_status` via same handler |
| Shareable Twin image badge | Story B.1 — flag rendered by `twin_image_renderer` when `user.is_founding_member` |
| Feedback triage flag | `backend/feedback/handlers/triage_command.py` — 🌱 emoji in inbox row |

Anywhere founding status is checked, the canonical predicate is
**`user.is_founding_member`** + sequence bounds check. Don't recompute
from invite codes — the flag is the source of truth, the invite is
the audit trail.

---

## When this doc gets updated

- **Phase 5.7 launch:** add a "Phase 5.7 implementation notes" section
  here recording how the four obligations above were satisfied. Move
  this file from `docs/current/` to `docs/conventions/` at that point.
- **Cap change:** require this doc to be touched in the same PR.
  Cap change without doc update = revert.
- **Discount math change:** same rule — doc + code in the same PR.
- **Promise reinterpretation:** add a numbered amendment at the bottom
  of the file with date + rationale + operator initials. Never
  silently edit the wording above.

---

*Original commitment: 12/05/2026 (Phase 4.1 soft launch).*
