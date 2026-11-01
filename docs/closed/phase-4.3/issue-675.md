# Issue #675

[Story 1.2] Life Outcome Translation via LLM — Phase 4.3

## Story 1.2 — Life Outcome Translation via LLM

**Parent Epic:** #670 | **Estimate:** 2 days | **Priority:** P0 | **Surface:** Telegram | **Depends on:** Story 1.1 (#674)

### User Story
> Là một mass affluent user, khi tôi thấy "5.2 tỷ năm 2030", con số đó không gợi cho tôi cảm xúc gì. Tôi muốn thấy "5.2 tỷ = đủ căn 2PN tại Q.7 + 1 tỷ tiết kiệm" để hình dung được tương lai.

### Requirements
- [ ] LLM service `life_outcome_translator.translate(amount_vnd, target_year, user_context)` → Vietnamese phrase ≤ 30 từ
- [ ] User context: location (city), known goals, age, dependents
- [ ] Prompt template với guardrails: KHÔNG promise certainty, KHÔNG specific brand, KHÔNG suggest actions
- [ ] Cache strategy: hash(amount_bucket, year, user_segment, location), TTL 7 ngày
- [ ] Amount bucketing: round to nearest 200tr
- [ ] Fallback nếu LLM unavailable: static lookup `life_outcome_fallback.yaml`
- [ ] Render only cho focused card (Bình thường mặc định)
- [ ] User có thể tap "Đổi ví dụ khác →" (max 3 lần/ngày)

### Files Touched
- `apps/twin_renderer/life_outcome_translator.py` (new)
- `prompts/life_outcome_v1.txt` (new)
- `content/twin/life_outcome_fallback.yaml` (new)
- `content/reference/vn_housing_price_q2_2026.yaml` (new)
- `infra/cache/life_outcome_cache.py` (new)

### Definition of Done
- [ ] All AC met
- [ ] 50-sample audit passed
- [ ] LLM cost within budget
- [ ] PR closes #675

