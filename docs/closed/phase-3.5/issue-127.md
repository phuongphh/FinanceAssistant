# Issue #127

[Story] P3.5-S14: Build advisory handler with rich context

**Parent Epic:** #112 (Epic 3: Personality & Advisory)

## User Story
As a user hỏi "làm thế nào để đầu tư tiếp?", tôi muốn context-aware advice xem xét actual portfolio, income, goals của tôi — không phải generic "hãy đa dạng hóa đầu tư".

## Acceptance Criteria
- [ ] File `app/intent/handlers/advisory.py` với `AdvisoryHandler`
- [ ] Handler build rich context trước LLM call:
  - User name + wealth level
  - Net worth + breakdown by asset type
  - Monthly income (sum of income_streams)
  - Active goals
  - Recent significant transactions (top 5 of last 30 days)
- [ ] `ADVISORY_PROMPT` template:
  - Tone instructions (Bé Tiền, Vietnamese, "mình"/"bạn")
  - Hard constraints: **KHÔNG recommend specific tickers** (legal), **KHÔNG promise returns**
  - Suggest 2-3 options, không 1 prescription
  - Hỏi lại nếu cần thêm info
- [ ] DeepSeek call: max_tokens=500, temperature=0.7
- [ ] **Disclaimer footer LUÔN append:**
  `_Đây là gợi ý dựa trên data cá nhân, không phải lời khuyên đầu tư chuyên nghiệp._`
- [ ] Test queries:
  - "làm thế nào để đầu tư tiếp?" → contextual options
  - "có nên mua VNM không?" → KHÔNG recommend, redirect general principles
  - "mình nên tiết kiệm bao nhiêu?" → calculation-based
  - "đầu tư crypto được không?" → balanced view, risks
- [ ] Rate limit: 5 advisory queries/user/day
- [ ] Disclaimer hiện trong 100% responses

## Estimate: ~1.5 day
## Depends on: Epic 2 complete
## Reference: `docs/current/phase-3.5-detailed.md` § 3.2
