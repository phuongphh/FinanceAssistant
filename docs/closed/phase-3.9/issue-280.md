# Issue #280

[Story] P3.9-S13: Bank rates scraper (top 20 banks)

**Parent Epic:** #265 (Epic 3: Gold + Bank Rates + News)

## ⚠️ Story lớn nhất phase (~2 ngày)

## User Story
As a system, I need to scrape lãi suất tiết kiệm từ 20 ngân hàng phổ biến nhất.

## Acceptance Criteria
- [ ] Folder `app/market_data/providers/bank_parsers/` với 20 file: vcb.py, bidv.py, agribank.py, ...
- [ ] Mỗi parser implement parse_rates(html) → list[BankRate]
- [ ] `bank_rates_scraper.py` orchestrator: fetch HTML → parse → gom kết quả
- [ ] Schema BankRate: bank_code, bank_name, tenor_months (1,3,6,12,24), rate_pct, deposit_type, notes
- [ ] DB migration: bảng bank_rates
- [ ] Mỗi bank có fixture HTML test
- [ ] **Banks tier 1 (MUST work):** VCB, BIDV, Agribank, Vietinbank, Techcombank, MBBank, ACB, VPBank
- [ ] **Banks tier 2 (OK fail 1-2):** còn lại (SHB, HDBank, Sacombank, VIB, OCB, MSB, TPBank, SeABank, LienVietPostBank, NamABank, PG Bank, PVComBank)
- [ ] Skip mechanism: bank fail → log + skip, không break job
- [ ] Job weekly, Monday 6am

## Technical Notes
- Một số bank dùng JS render → có thể cần Playwright/Selenium
- Đây là Story lớn → có thể split sub-tasks

## Estimate: ~2 days
## Depends on: P3.9-S1, P3.9-S2
