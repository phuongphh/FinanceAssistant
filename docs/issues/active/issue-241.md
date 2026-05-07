# Issue #241

[Epic] Phase 3.8.5 — Epic 1: Feedback System

## Phase 3.8.5 — Epic 1: Feedback System

> **Type:** Epic | **Day:** 1-2 | **Stories:** 3

## Context
Phase 3.8.5 là **Pre-Launch Readiness** — inserted giữa Phase 3.8 và Phase 3.9, chuẩn bị soft launch tháng 6/2026. Epic 1 build feedback loop critical cho product iteration.

## Triết Lý "Zero Friction Feedback"
User chỉ cần 2 actions: `/feedback` + type/voice. **Không** chọn category, **không** chọn priority, **không** điền form. Backend tự classify via DeepSeek. Maximize feedback volume.

## Tại Sao Epic Này Critical
Soft launch mà không có feedback loop = launch blind. Không biết user gặp vấn đề gì, không biết iterate gì. Đây là **pre-launch infrastructure**, không phải nice-to-have.

## Success Definition
- ✅ `/feedback` command working, free-form text
- ✅ Backend auto-classify: category, sentiment, priority
- ✅ Active prompts trigger sau key events (max 4-6 lần/năm)
- ✅ Cooldown + rate limit prevent spam
- ✅ Admin query được feedback database

## Stories in this Epic
_(Sẽ update sau khi tạo Story issues)_
- [ ] [Story] P3.8.5-S1: Feedback model + /feedback command handler
- [ ] [Story] P3.8.5-S2: Backend auto-classification (DeepSeek)
- [ ] [Story] P3.8.5-S3: Active prompts scheduler

## Dependencies
✅ Phase 3.8 complete

## Reference
`docs/current/phase-3.8.5/phase-3.8.5-detailed.md` § Feedback System
