# Issue #603

fix(ocr): wire photo message handler in telegram_worker to call ocr_service

## Bug
Sending a receipt photo to the bot produces no response. The backend accepts the message and immediately marks it as "done" without calling OCR.

## Root cause
`telegram_worker.py` has no handler for photo/image messages. Although `ocr_service.py` exists with `parse_receipt_image()`, it is never invoked when a user sends a photo.

## Steps to reproduce
1. Send a photo of a receipt to the bot
2. Bot responds with nothing (silent done)

## Expected behavior
- Bot detects photo message
- Downloads the image from Telegram
- Calls `ocr_service.parse_receipt_image()`
- Returns structured receipt info or error message

## Files to modify
- `backend/workers/telegram_worker.py` — add photo message handler
- `backend/services/ocr_service.py` — already exists, just needs to be wired

## Config needed
- `OCR_API_URL=https://ocr.nuitruc.ai/api/v1/ocr/extract` (already in .env)
- `OCR_API_KEY=` (public, no key needed)

## Acceptance criteria
- [ ] Sending a receipt photo triggers OCR
- [ ] Bot replies with receipt info (amount, merchant, items)
- [ ] Non-receipt photos return a friendly "not a receipt" message
