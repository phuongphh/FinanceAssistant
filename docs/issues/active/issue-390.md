# Issue #390

[Story] P4A-S16: LLM narrative ("Bé Tiền năm 2036")

**Parent Epic:** #371 (Epic 3: Telegram Twin Surface)

## Description
Optional Tier 2 LLM call generates 2-3 sentence narrative from cone data. Cached 7 days.

## Acceptance Criteria
- [ ] Prompt template in content/twin_copy.yaml
- [ ] Call via existing llm_service (DeepSeek)
- [ ] Cache: user_id + cone_hash, TTL 7 days
- [ ] Output 50-200 chars, no markdown
- [ ] Template fallback if LLM fail
- [ ] prompt-tester agent pass

## Estimate: ~0.5 day
## Dependencies: P4A-S11

Close #371
