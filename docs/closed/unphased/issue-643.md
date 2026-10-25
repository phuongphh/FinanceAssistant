# Issue #643

improve: Reword Bé Tiền note in Asset menu with natural tone

## Summary
Reword the Bé Tiền note in the Asset menu to use a natural, chatty tone.

## Motivation
The current note text is too technical. As a chat-first product, Bé Tiền should speak naturally to users. The new text should feel like Bé Tiền is personally updating the user about their assets.

## Requirements
- [ ] Replace current note with: "Tài sản của bạn đã được Bé Tiền cập nhật dựa trên giá trị mới nhất của thị trường chứng khoán, vàng và tiền số"
- [ ] Use Bé Tiền's natural, friendly, chatty tone
- [ ] Keep the same position and styling in the UI

## Technical Notes
- Affected file(s): Asset menu view — Bé Tiền note section
- Text change only, no structural changes

## Acceptance Criteria
- [ ] New text is displayed correctly
- [ ] Tone matches Bé Tiền's friendly personality
- [ ] No layout or styling changes

## Out of Scope
- Adding additional notes or features
- Changing the position of the note

## Claude Code Implementation Prompt
```
Read GitHub issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Replace the Bé Tiền note text in Asset menu with:
"Tài sản của bạn đã được Bé Tiền cập nhật dựa trên giá trị mới nhất của thị trường chứng khoán, vàng và tiền số"

Guidelines:
- Branch: improve/be-tien-note-text
- Text change only — no structural or style changes
- Conventional commits
- Create draft PR linking to issue #[ISSUE_NUMBER]
```

