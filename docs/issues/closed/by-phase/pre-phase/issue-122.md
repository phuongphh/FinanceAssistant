# Issue #122

[Story] P3.5-S9: Create clarification message templates (YAML)

**Parent Epic:** #111 (Epic 2: LLM Fallback & Clarification)

## User Story
As a content owner, I want clarification messages stored in editable YAML so I can refine wording without code changes khi user testing reveals confusing prompts.

## Acceptance Criteria
- [ ] File `content/clarification_messages.yaml` với templates cho:
  - `low_confidence_assets` — disambiguate which asset type
  - `low_confidence_expenses` — ask which time period
  - `low_confidence_market` — ask which ticker
  - `low_confidence_action` — disambiguate save/spend/goal
  - `ambiguous_amount` — confirm parsed amount
  - `ambiguous_category` — choose from list
  - `awaiting_response` — generic waiting message
- [ ] 2-3 variations per type (avoid repetition)
- [ ] Placeholders: {name}, {amount}, {ticker}, etc.
- [ ] Templates designed với inline keyboard buttons trong mind
- [ ] Tone matches Bé Tiền personality (warm, "mình"/"bạn")
- [ ] yamllint passes

## Sample
```yaml
low_confidence_assets:
  - |
    Mình hiểu bạn hỏi về tài sản, nhưng chưa rõ chi tiết...
    Bạn muốn:
    [📊 Xem tổng tài sản]
    [🏠 Chỉ BĐS]
    [📈 Chỉ chứng khoán]
    [💵 Chỉ tiền mặt]
```

## Estimate: ~0.5 day
## Depends on: P3.5-S8
