# Issue #907

Onboarding: resume nudge collides with name/salutation sub-steps ("two flows at once")

## Symptom

During V2 onboarding (first-5-minutes WOW), a new user sees **two flows fire at once**:

1. When asked for their name and they type e.g. `P`, two messages arrive simultaneously — the Twin-onboarding **resume nudge** ("Bé Tiền đang chờ bạn ở bước *câu hỏi mục tiêu* … Tiếp tục nhé?") *and* the live first-5-min-wow salutation question.
2. Tapping the salutation/gender button again triggers two flows → two messages → and the live Reading/number-input flow can no longer be completed.

Net effect: the minute-1 intro (name → salutation → goal) gets forked and the user is stranded.

## Root cause

Name entry and salutation pick are **collapsed into the single `goal_question` DB step** (`OnboardingSession.current_step`); the live sub-step is only derivable from the `User` row. Crucially, those sub-steps mutate the **`User`** row (`set_display_name` / `set_salutation`), never the **`OnboardingSession`** row — so `OnboardingSession.updated_at` stays frozen at `/start` time while the user is on name/salutation.

Consequences:
- The resume-nudge cron (every 5 min; fires for sessions "stuck >10 min" on `goal_question`, one nudge per user ever) mis-classifies a name-entry user as *stuck at goal pick* and fires a Twin-centric nudge mid-intro — off-message and premature ("WOW first, Twin payoff").
- That nudge's **Tiếp tục** → `_resume_at(goal_question)` → `_send_goal_question()` **skips name + salutation**, forking the flow.

## Fix

No migration — derive the sub-step from existing columns:
- `onboarding_service.goal_substep(user)` → `name` → `salutation` → `goal`.
- `_resume_at` for `goal_question` resumes at the **correct sub-step** (re-send name prompt / salutation question / goal question) instead of jumping to goal.
- Resume-nudge job **skips** the name/salutation intro sub-steps (`_is_intro_substep`), leaving `nudge_sent_at` NULL so the user stays eligible once they reach goal pick / asset / twin.

Twin payoff at minute-4 is untouched (no regression).

## Acceptance
- [ ] No nudge fires during name/salutation sub-steps.
- [ ] Resume never skips name/salutation.
- [ ] Unit tests for `goal_substep`, `_resume_at` routing, and the job skip predicate.
