# Issue #213

[Story] P3.8-S5: Income wizard via Telegram menu

**Parent Epic:** #205 (Epic 2: Multi-Income Streams)

## User Story
As a user, tôi muốn add/manage nhiều nguồn thu nhập qua Telegram menu với UX rõ ràng.

## Acceptance Criteria
- [ ] **Update Phase 3.6 menu** action `menu:cashflow:income`:
  - List current streams + button "➕ Thêm thu nhập mới"
- [ ] **Wizard flow:**
  - Q1: "Loại thu nhập?" — 6 buttons với emojis
  - Q2: "Số tiền?" — parse VND
  - Q3: "Bao lâu nhận?" [Hàng tháng] [Hàng quý] [Hàng năm] [Bất định]
  - Q4 (if monthly): "Ngày nào trong tháng?" (1-31)
  - Q4 (if annually): "Tháng nào?" (1-12)
  - Q5: "Ngày bắt đầu?" [Hôm nay] [Tự nhập]
- [ ] **Auto-create rental stream** khi BĐS được mark là rental (link source_asset_id)
- [ ] **List view:**
  - Mỗi stream: icon + name + amount + schedule
  - Total monthly equivalent
  - Active/passive ratio bar
  - Edit/Delete per stream
- [ ] **Empty state:** "Chưa có nguồn thu nào. Thêm cái đầu tiên!"

## Estimate: ~1 day
## Depends on: P3.8-S4
