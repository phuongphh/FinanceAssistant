# Issue #160

[Epic] Phase 3.6 — Epic 3: Migration & Quality Assurance

## Phase 3.6 — Epic 3: Migration & Quality Assurance

> **Type:** Epic | **Week:** 2 (1/2) | **Stories:** 3

## Mục tiêu
Execute hard cutover migration: pre-announce → deploy → post-announce → user test → cleanup. Menu mới live cho tất cả users, code cũ archived, user feedback collected.

## Tại Sao Epic Này Quan Trọng
Phase 3.6 success phụ thuộc vào **smooth deploy**. Users hiện đang rely on old menu — switching có thể disorient. Hard cutover với announcement minimize confusion. User testing 24-48h post-deploy catch issues sớm.

## Success Definition
- ✅ New menu live cho 100% users
- ✅ Old menu code archived (không deleted)
- ✅ Pre-announcement + post-announcement messages sent
- ✅ ≥3 users tested new menu, feedback positive
- ✅ Documentation updated (CLAUDE.md, strategy.md, README)

## Stories in this Epic
_(Sẽ update sau khi tạo Story issues)_
- [ ] [Story] P3.6-S11: Prepare and execute hard cutover deploy
- [ ] [Story] P3.6-S12: User testing with 3 users post-deploy
- [ ] [Story] P3.6-S13: Cleanup, archive, and documentation updates

## Dependencies
✅ Epic 1 + Epic 2 complete

## Reference
`docs/current/phase-3.6-detailed.md` § 2.2 — Migration Strategy
