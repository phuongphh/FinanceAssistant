# Issue #125

[Story] P3.5-S12: Add personality wrapper to query responses

**Parent Epic:** #112 (Epic 3: Personality & Advisory)

## User Story
As a user, khi tôi hỏi "tài sản của tôi có gì?", tôi không muốn sterile data dump. Tôi muốn Bé Tiền greet tôi, present info warmly, và feel like nó biết về tôi.

## Acceptance Criteria
- [ ] File `app/bot/personality/query_voice.py` với `add_personality(response, user, intent_type) -> str`
- [ ] 30% probability: prepend warm greeting với user.display_name
- [ ] 50% probability: append next-action suggestion related to intent
- [ ] 5+ greeting variations:
  - "{name} ơi,"
  - "Hiểu rồi {name}!"
  - "Cho mình check liền,"
  - "Có ngay {name}!"
  - "{name}, đây nè:"
- [ ] 5+ suggestion variations per intent:
  - query_assets → "Muốn xem chi tiết phần nào?"
  - query_expenses → "So sánh với tháng trước không?"
  - query_market → "Xem chi tiết phân tích không?"
- [ ] Integrate vào IntentDispatcher: wrap handler result trước khi send
- [ ] **Test: Same query 5 lần → 3+ different opening phrases** (variation working)
- [ ] **Test: Generic phrases NEVER appear** ("Here are your assets", "Following are...")
- [ ] **KHÔNG inject personality vào clarification hoặc error messages**

## Estimate: ~1 day
## Depends on: Epic 2 complete
## Reference: `docs/current/phase-3.5-detailed.md` § 3.1
