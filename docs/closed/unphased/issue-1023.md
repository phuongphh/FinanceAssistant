# Issue #1023

FinanceAssistant: market snapshot sync fails after VNINDEX DB save

Nguyên nhân ghi nhận từ log dev Mac Mini ngày 2026-08-11:

- Scheduler `market_snapshot` chạy lúc 08:00 và có ghi `market_snapshots` cho `VNINDEX` ngày 2026-08-11 trong Postgres.
- Sau khi DB save, bước `sync_market_snapshot_to_notion` lỗi lặp lại với thông báo: `Could not find database with ID: 32dde363-4d5c-80fc-a0f8-c054a8a824e9. Make sure the relevant pages and databases are shared with your integration "FinanceAssistant".`
- Vì vậy phần không thấy lưu/sync ra ngoài nằm ở Notion sync sau DB save, không phải dòng `VNINDEX` trong Postgres dev.
- Ghi nhận phụ: các snapshot VN30 individual stocks cùng ngày đang có nhiều giá `0.0000`, trong khi `VNINDEX` chính có giá `1776.7700`.

Log mốc:
- `scheduler.error.log` khoảng 2026-08-11 08:00:02: insert/update `market_snapshots` cho `VNINDEX` và VN30.
- `scheduler.error.log` khoảng 2026-08-11 08:00:11-08:00:19: Notion database ID không tìm thấy.
