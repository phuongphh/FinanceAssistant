# Issue #976

[Phase 4.5 / E4] 4.1 — export_service + /export entry

`backend/services/export/export_service.py` (openpyxl, 3 sheets Tài sản/Thu chi/Mục tiêu, `Decimal`); command `/export` + intent + nút menu báo cáo; gửi qua Telegram `sendDocument` (adapter). Flag `EXPORT_EXCEL_ENABLED` default `true`.

**DoD:**
- [ ] File mở được (openpyxl round-trip test)
- [ ] Số khớp DB
- [ ] User trống → file có header không crash
- [ ] Test flag off

Epic: #962 · Detail: `docs/current/phase-4.5/phase-4.5-issues.md`
