# Issue #340

[Story] P3.9.5-S2: Bỏ button "Phân bổ chi tiết" + sửa logic YTD return

**Parent Epic:** #334 (Epic 1: Tài sản)

## Description
Button "Phân bổ chi tiết" trùng chức năng → xoá. Button "YTD return" logic sai — cần fix tính từ 1/1/year.

## Acceptance Criteria
- [ ] Button "Phân bổ chi tiết" xoá khỏi menu báo cáo chi tiết tài sản
- [ ] YTD return computed đúng: từ 1/1/current_year → today, base = net worth tại 1/1, return = (current - base) / base * 100%
- [ ] Edge: account < 1 năm → fallback "Từ ngày tham gia: X%"
- [ ] Edge: zero base → display "—" thay vì divide-by-zero
- [ ] Unit test YTD calc: full year, partial year, zero base
- [ ] Display format: "+5.2%" or "-3.1%" với 📈/📉

## Estimate: ~0.5 day
## Dependencies: None

Close #334
