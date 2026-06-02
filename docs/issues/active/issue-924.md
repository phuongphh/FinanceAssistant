# Issue #924

[UI] Redesign card-style edit screens: full-width content + ✏️ Sửa / 🗑 Xoá action row

## Problem

On the "sửa tài sản" (edit assets) screen, each asset row is a 2-button Telegram inline-keyboard row: a left button carrying the content (e.g. `✏️ 🏛️ VCB — 100 tỷ`) and a right button containing only a trash icon (🗑).

Telegram renders buttons **within the same row at equal width** regardless of text length, so the trash button claims ~50% of the row width. That leaves the content button too little space and the asset name gets truncated/unreadable.

## Desired design

For every card-style edit screen, show the row **content on its own full-width line**, then place an **edit button (✏️ Sửa)** and a **delete button (🗑 Xoá)** on a second action row beneath it.

This must apply consistently to all card-style edit screens:
- Sửa tài sản (asset dashboard edit)
- Sửa chứng khoán (market edit list — stock/crypto/gold)
- Sửa tài sản khi đã filter (e.g. "tài sản TCB…", subtype-filtered edit list)

## Acceptance criteria

- [ ] Each asset card = a full-width content label row + an action row with ✏️ Sửa / 🗑 Xoá
- [ ] No standalone trash-icon button sharing the content row
- [ ] Consistent across dashboard edit, market edit list, and subtype-filtered edit list (shared builder)
- [ ] Content-label tap is a deliberate no-op (real actions live on the action row)
- [ ] Edit routes to the existing edit wizard; delete routes through the existing delete-confirm guard
- [ ] All callbacks stay within Telegram's 64-byte cap; keyboards stay under the reply_markup size budget (pagination preserved)
- [ ] Full unit test coverage

## Notes

- Bé Tiền persona / Vietnamese localization unchanged.
- Money formatting unchanged (`currency_utils.format_money_short`).

