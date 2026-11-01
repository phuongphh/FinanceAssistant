# Issue #439

[Story] P4B-S22: ZaloNotifier implementing Notifier Port

**Parent Epic:** #417 (Epic 4: Zalo Adapter Foundation)

## User Story
La developer, toi muon ZaloNotifier hoat dong nhu TelegramNotifier.

## Implementation Tasks
- [ ] adapters/zalo_notifier.py: class ZaloNotifier(Notifier)
- [ ] strip_markdown(): loai bo *, _, formatting
- [ ] Truncate 300 chars (Zalo limit)
- [ ] send(message), send_image(image_bytes, caption)
- [ ] Pass shared notifier_test_suite.py

## Estimate: ~1 day
## Depends on: P4B-S21

Close #417
