# Issue #644

improve: Add asset category note in Asset Management

## Summary
Add a note in the Asset Management menu listing the asset categories included.

## Motivation
Users need clarity on what types of assets are being managed. A brief note listing categories (cash, securities, real estate, crypto, gold, etc.) helps users understand the scope.

## Requirements
- [ ] Add a note in Asset Management menu showing: "Tài sản gồm những gì (Tiền mặt & Tài khoản, Chứng khoán, Bất động sản, Tiền số, Vàng…)"
- [ ] Use Bé Tiền's natural tone
- [ ] Place note at the top of the Asset Management screen

## Technical Notes
- Affected file(s): Asset Management view
- Text/non-interactive note element

## Acceptance Criteria
- [ ] Note is visible at top of Asset Management
- [ ] Lists all supported asset categories
- [ ] Uses user-friendly, natural language

## Out of Scope
- Interactive elements or navigation from the note

## Claude Code Implementation Prompt
```
Read GitHub issue #[ISSUE_NUMBER] in phuongphh/FinanceAssistant.

Add a note at the top of Asset Management menu:
"Tài sản gồm những gì (Tiền mặt & Tài khoản, Chứng khoán, Bất động sản, Tiền số, Vàng…)"

Use Bé Tiền's natural tone. Non-interactive text element.

Guidelines:
- Branch: improve/asset-note-categories
- Conventional commits
- Create draft PR linking to issue #[ISSUE_NUMBER]
```

