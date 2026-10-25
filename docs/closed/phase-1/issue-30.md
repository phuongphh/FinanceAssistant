# Issue #30

[Phase 1 - Week 4] Visual Identity — Bot Name, Mascot & Tone Writing

## User Story
As a product owner, I want the bot to have a consistent name, mascot, and warm tone so that users feel they are interacting with a friendly personal assistant, not a cold banking system.

## Background
Phase 1 - Week 4 polish tasks. Non-code tasks included — coordinate with design if needed.

## Tasks
- [ ] **Choose bot name** — brainstorm 5 options (e.g. Xu, Tiết, Chi, Finny, Bông), pick 1 that is short, memorable, and friendly
- [ ] **Create mascot** — 3 expressions required: happy, worried, celebrating
  - Option A: Hire on Fiverr ($50–100, search "chibi mascot finance")
  - Option B: Generate with Midjourney (chibi piggy bank character, minimalist vector, Vietnamese finance app)
- [ ] **Update bot profile picture** in BotFather — 512×512, clean white background
- [ ] **Update bot description** in BotFather via /setdescription
- [ ] **Create `docs/tone_guide.md`** with:
  - Xưng hô rules (mình / bạn)
  - Principles: short, warm, non-judgmental, offer choices
  - Word replacement table (avoid → use)
  - Emoji usage guide
- [ ] **Audit all bot messages** — apply tone guide, remove cold/robotic phrases
- [ ] **Run friends beta test**: 5–10 people, collect feedback via Google Form (5 questions)
- [ ] **Interview 2–3 users** via video call, compile insights

## Acceptance Criteria
- [ ] Bot has a final name and updated BotFather profile
- [ ] Mascot exists in at least 3 expressions (image files in `assets/mascot/`)
- [ ] `docs/tone_guide.md` is written and reviewed
- [ ] All bot messages follow tone guide (no "Hệ thống đã lưu", no "Vui lòng")
- [ ] At least 5 friends have tested and submitted feedback
- [ ] Feedback compiled into actionable list for bug fix sprint

## Reference
`docs/strategy/phase-1-detailed.md` — Section 4.1 – 4.4
