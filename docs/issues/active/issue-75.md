# Issue #75

[P3A-17] Write & test storytelling LLM prompt (accuracy ≥80%)

## Epic
Epic 3 — Storytelling Expense | **Week 3** | Depends: P3A-16 | Blocks: P3A-18

## ⚠️ Critical Issue — Start Early
Đây là issue quan trọng nhất Epic 3. LLM prompt quyết định accuracy toàn bộ feature. **Cần test iteratively**, không thể rush.

## Description
Write và test LLM prompt để extract giao dịch từ câu chuyện tự nhiên của user.

## Acceptance Criteria
- [ ] File `app/bot/personality/storytelling_prompt.py` với `STORYTELLING_PROMPT` constant
- [ ] Function `extract_transactions_from_story(story, user_id, threshold) -> dict`
- [ ] Integration với DeepSeek API (primary)
- [ ] Output JSON schema:
  ```json
  {
    "transactions": [{"merchant": ..., "amount": ..., "category": ...}],
    "needs_clarification": [{"text": ..., "reason": ...}],
    "ignored_small": [{"text": ..., "amount": ...}]
  }
  ```
- [ ] **Test suite với 30+ câu chuyện mẫu** (minimum):
  - Đơn giản: "Tối qua ăn nhà hàng 800k"
  - Phức tạp: nhiều giao dịch trong 1 câu
  - Ngàn: "mua điện thoại 15 triệu"
  - Chia sẻ: "ăn với bạn 400k chia đôi" → extract 200k
  - Dưới threshold: với threshold=200k, ignore giao dịch nhỏ hơn
  - Không giao dịch: "đi chơi với bạn" → transactions=[]
  - Ambiguous: "mua đồ" → needs_clarification
  - Voice transcript (có thể sai chính tả, thiếu dấu)
- [ ] Accuracy ≥80% trên test suite
- [ ] Cost per call </tmp/create_p3a_epic3_4.sh.01
- [ ] Fallback nếu LLM error → ask user nicely
- [ ] Logging mọi call để debug

## Technical Notes
- Test iteratively — chạy suite, tinh chỉnh prompt, lặp
- Cache identical stories (hash-based)
- Tiếng Việt có dấu và không dấu phải xử lý tốt

## Estimate
~1.5 day

## Reference
`docs/current/phase-3a-detailed.md` § 3.2
