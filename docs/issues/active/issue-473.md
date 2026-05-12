# Issue #473

[Story] P4.1-B1: Shareable Twin image

**Parent Epic:** #464 (Epic B: Twin Polish)

## Description
Trong Twin view, them nut "Luu thanh anh" tra ve PNG render cua cone chart + summary. KHONG chua so tuyet doi.

## Acceptance Criteria
- [ ] Nut "Luu thanh anh" trong Twin view
- [ ] PNG via PIL/Pillow (target < 1s)
- [ ] Content: cone chart, % tang truong compounded, time horizon, mascot, watermark
- [ ] KHONG hien so tien tuyet doi
- [ ] KHONG auto-prompt share
- [ ] Render headless, khong Chrome/Puppeteer
- [ ] Feature flag TWIN_SHARE_IMAGE_ENABLED

## Estimate: ~2 days
## Dependencies: None (Twin view tu 4A)

Close #464
