# Issue #854

OCR receipt flow drops transfer note and skips category selection

## Bug

When a user photographs a bank-transfer receipt, the OCR pipeline returns the **full** text — including the transfer memo ("Lời nhắn" / "Nội dung giao dịch"), recipient name and transaction code — but the saved expense **loses the note**. It only stores amount + date + category (defaulting to "Khác").

Example (Techcombank transfer, 2,700,000đ): the memo `Link power chuyển tiền so do thua dat 841` is read correctly by OCR but never persisted on the expense.

Separately, the user has **no way to pick the category before confirming**. The receipt is auto-categorized (often to "Khác") and the confirmation only offers Đồng ý / Huỷ.

## Tasks

- [ ] **Task 1 — Note:** Extract the receipt's "lời nhắn" / "nội dung giao dịch" line (label varies per receipt) and persist it onto the expense. Fall back to an item-name preview when no memo is present.
- [ ] **Task 2 — Category picker:** Show a list of "danh mục" so the user can choose the category **before** confirming, while keeping the existing Đồng ý / Huỷ buttons.

## Requirements

- Consistency across the two category-code namespaces (schema vs display).
- Fast response (re-render in place, no extra round-trips).
- UI/UX in the warm "Bé Tiền" persona.
- Security: bound note length, render confirmation as raw text (no HTML injection), guard the pending-confirm token by ownership + TTL + valid code.
- Full unit tests.
