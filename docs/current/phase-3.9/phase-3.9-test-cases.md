# Phase 3.9 — Manual Test Cases

> **Purpose:** Comprehensive manual test cases cho Phase 3.9 (Market Data Real)
> **Tester Profile:** No source code access. Tests via Telegram bot, owner admin tools, và direct DB query (read-only).
> **Reference:** [phase-3.9-detailed.md](./phase-3.9-detailed.md), [phase-3.9-issues.md](./phase-3.9-issues.md)
> **Total cases:** 88 (across 10 sections)

---

## How to Use This Document

### Test Case Structure

```
TC-XXX: [Title]
Type: Happy | Provider | Cache | Job | Performance | Regression | Critical
Story: P3.9-Sn (links to issue)
Persona: Which test user/setup
Preconditions: State required before test
Steps: Numbered actions
Expected Results: Observable outcomes
Pass Criteria: All expected results met
```

### Pass / Fail Criteria

- ✅ **PASS:** All Expected Results observed
- ⚠️ **PASS WITH NOTES:** Main behavior correct, minor issues
- ❌ **FAIL:** Any Expected Result not observed
- 🚫 **BLOCKED:** Cannot execute due to dependency

---

## Test Data Setup

Reuse 4 personas từ Phase 3.7/3.8/3.8.5, mở rộng với holdings cụ thể cho test market data:

### Persona 1: Hà (Young Professional, 140tr)
- Stocks: VNM (200), HPG (100), VIC (50), FPT (30)
- Crypto: BTC (0.05), ETH (0.5)
- Vàng: 2 chỉ SJC
- Cash: 50tr tại VCB

### Persona 2: Phương (Mass Affluent, 2.5 tỷ)
- Stocks: 8 mã đa dạng (VNM, HPG, VIC, FPT, GAS, MWG, VCB, MSN)
- Crypto: BTC (0.5), ETH (5), SOL (50)
- Vàng: 5 lượng SJC
- Cash: 500tr tại MB
- Real estate: 1 BĐS Q7 (1.5 tỷ user-input)

### Persona 3: Minh (HNW, 8 tỷ)
- Stocks: 15+ mã
- Crypto: portfolio đa dạng
- Vàng: 20 lượng
- Cash: 1 tỷ chia tại 3 ngân hàng (VCB, ACB, VPB)
- Real estate: 2 properties

### Persona 4: BrandNew (Starter, 0 tài sản)
- Vừa onboard, chưa có holdings
- Test edge case: briefing render với portfolio rỗng

### Test Symbol Set (cho provider tests)
- Stocks: VNM, HPG, VIC, FPT (popular), VRE, KDH (mid-cap), 1 UPCOM stock
- Crypto: BTC, ETH, SOL, BNB, DOGE, 1 unsupported (vd: "INVALID")
- Gold: SJC_GOLD, RING_24K
- Banks: VCB, BIDV, Techcombank (test parsers tier 1)

---

# Section 1: Stock Provider (Stories S4, S5)

## TC-001: SSI provider — happy path single quote
**Type:** Provider | **Story:** P3.9-S4
**Preconditions:** SSI iBoard reachable, Redis flushed cho `market_data:stock:VNM`

**Steps:**
1. Owner gọi internal endpoint `GET /admin/market-data/test-fetch?provider=ssi&symbol=VNM`

**Expected Results:**
- HTTP 200 response
- Response JSON: `{symbol: "VNM", price: <number>, currency: "VND", source: "ssi", fetched_at: <ISO timestamp>}`
- Price là số dương > 1000 (sanity check, VNM giá thường 60-80k)
- `metadata` chứa `volume`, `change_pct`
- Latency < 3 giây

---

## TC-002: SSI provider — invalid symbol
**Type:** Provider | **Story:** P3.9-S4

**Steps:**
1. Owner gọi `GET /admin/market-data/test-fetch?provider=ssi&symbol=NOTREAL`

**Expected Results:**
- HTTP 404 hoặc structured error: `{error: "SymbolNotFound", message: "..."}`
- Log entry với `level=WARN`, không phải ERROR

---

## TC-003: VNDIRECT provider — happy path
**Type:** Provider | **Story:** P3.9-S5

**Steps:**
1. Owner gọi `GET /admin/market-data/test-fetch?provider=vndirect&symbol=HPG`

**Expected Results:**
- Response tương tự TC-001 nhưng `source: "vndirect"`
- Price match SSI ± 1% (cross-validate)

---

## TC-004: Stock dispatcher — fallback when SSI down
**Type:** Critical | **Story:** P3.9-S5

**Preconditions:** Inject mock fail cho SSI (vd: feature flag `SSI_FORCE_FAIL=true`)

**Steps:**
1. Gọi `GET /admin/market-data/test-fetch?provider=auto&symbol=VNM`

**Expected Results:**
- Response thành công
- `source: "vndirect"` (fallback đã kích hoạt)
- Log có entry: `"SSI failed for VNM, fallback to VNDIRECT"`
- Disable mock fail sau test

---

## TC-005: Circuit breaker — opens after 5 failures
**Type:** Critical | **Story:** P3.9-S3

**Preconditions:** Reset circuit state Redis key `market_data:health:ssi:*`

**Steps:**
1. Force SSI fail (mock) trong vòng 60s, gọi 5 lần liên tiếp
2. Gọi lần 6 trong vòng 5 phút sau khi circuit open

**Expected Results:**
- Lần 1-5: log "SSI failed", fallback VNDIRECT mỗi lần
- Sau lần 5: log `"Circuit OPEN for ssi"`
- Lần 6: KHÔNG log "SSI failed" (vì skip trực tiếp), log "Circuit OPEN, using vndirect"
- Sau 5 phút: lần kế tiếp log "Circuit HALF-OPEN", thử SSI lại

---

## TC-006: Stock batch fetch
**Type:** Performance | **Story:** P3.9-S4

**Steps:**
1. Gọi `GET /admin/market-data/test-batch?provider=ssi&symbols=VNM,HPG,VIC,FPT`

**Expected Results:**
- Response chứa 4 quotes
- Tổng latency < 1.5s (faster than 4 sequential calls)
- Tất cả quotes cùng `fetched_at` (gần nhau)

---

# Section 2: Crypto Provider (Story S6)

## TC-007: CoinGecko — BTC quote
**Type:** Provider | **Story:** P3.9-S6

**Steps:**
1. Gọi `GET /admin/market-data/test-fetch?provider=coingecko&symbol=BTC`

**Expected Results:**
- Price > 100tr VND (sanity, BTC giá trên 100tr)
- `currency: "VND"` (không phải USD)
- `metadata` có thể có `price_usd`, `change_24h`

---

## TC-008: CoinGecko — unsupported symbol
**Type:** Provider | **Story:** P3.9-S6

**Steps:**
1. Gọi `GET /admin/market-data/test-fetch?provider=coingecko&symbol=INVALID`

**Expected Results:**
- Error `SymbolNotFound`
- Log mention "no mapping for INVALID"

---

## TC-009: CoinGecko — rate limit handling
**Type:** Critical | **Story:** P3.9-S6

**Preconditions:** Có thể test bằng cách gọi rất nhiều lần liên tiếp (>30 trong 1 phút)

**Steps:**
1. Loop 50 calls trong 30 giây cho `BTC`

**Expected Results:**
- Một số call bị rate limit (HTTP 429)
- Logic exponential backoff: thấy log "Retry in 1s", "Retry in 2s", "Retry in 4s"
- Không phải tất cả call fail (cache giúp một phần)

---

# Section 3: Gold Provider (Stories S10, S11, S12)

## TC-010: SJC parser — happy path
**Type:** Provider | **Story:** P3.9-S10

**Steps:**
1. Gọi `GET /admin/market-data/test-fetch?provider=sjc&symbol=SJC_GOLD`

**Expected Results:**
- Price > 70tr VND/lượng (sanity, vàng SJC range thực tế)
- `metadata.buy_price` < `metadata.sell_price` (giá bán cao hơn mua)
- `metadata.sjc_updated_at` là timestamp gần đây (hôm nay hoặc hôm qua)

---

## TC-011: SJC parser — fixture test
**Type:** Provider | **Story:** P3.9-S10

**Preconditions:** `tests/fixtures/sjc_sample.html` tồn tại

**Steps:**
1. Run unit test `pytest tests/market_data/providers/test_gold_sjc.py::test_parse_fixture`

**Expected Results:**
- Test pass
- Parser extract đúng giá từ fixture

---

## TC-012: PNJ fallback when SJC parser breaks
**Type:** Critical | **Story:** P3.9-S11

**Preconditions:** Mock SJC HTML response trả về invalid HTML (vd: empty response)

**Steps:**
1. Gọi `GET /admin/market-data/test-fetch?provider=auto&asset_type=gold`

**Expected Results:**
- Response thành công
- `source: "pnj"`
- Log: `"SJC parser error: ..., fallback to PNJ"`

---

## TC-013: Gold updater job runs
**Type:** Job | **Story:** P3.9-S12

**Steps:**
1. Trigger job manual: `POST /admin/jobs/run?name=gold_updater`
2. Check Redis cho key `market_data:gold:SJC_GOLD`

**Expected Results:**
- Job chạy thành công, log `"gold_updater: fetched 2 symbols"` (SJC + RING)
- Redis key tồn tại với TTL ~3600s
- `last_known` key cũng được set (no TTL)

---

# Section 4: Bank Rates (Story S13)

## TC-014: VCB parser — happy path
**Type:** Provider | **Story:** P3.9-S13

**Steps:**
1. Gọi `GET /admin/bank-rates/test-fetch?bank=vcb`

**Expected Results:**
- Response chứa list rates cho 5 tenors (1m, 3m, 6m, 12m, 24m)
- Mỗi rate: 0% < rate_pct < 15% (sanity check)
- Field `deposit_type` có giá trị hợp lệ

---

## TC-015: Bank rates orchestrator — partial failure resilience
**Type:** Critical | **Story:** P3.9-S13

**Preconditions:** Mock 2 banks fail (vd: simulate HTTP 500 cho BIDV và VPB)

**Steps:**
1. Trigger `POST /admin/jobs/run?name=bank_rates_updater`

**Expected Results:**
- Job complete, không crash
- Log có 2 warnings cho BIDV và VPB
- DB `bank_rates` table có entries cho 18/20 banks
- Job duration < 90s (slower vì fail retry, vẫn acceptable)

---

## TC-016: Bank rates query API
**Type:** Happy | **Story:** P3.9-S13
**Persona:** Phương

**Steps:**
1. Phương gửi tin nhắn Telegram: "lãi suất ngân hàng"

**Expected Results:**
- Bot trả về top 5 banks với rate cao nhất (12m tenor)
- Format dễ đọc, có persona Bé Tiền
- Each line: bank name, rate, last updated date

---

## TC-017: Bank rates — VCB rate change detection
**Type:** Critical | **Story:** P3.9-S13

**Preconditions:** Phương đang gửi 200tr tại VCB lãi 4.5%

**Steps:**
1. Mock VCB rate update từ 4.5% lên 5.2%
2. Trigger weekly bank rates job
3. Phương check briefing sáng

**Expected Results:**
- Briefing có insight: "Lãi suất VCB tăng từ 4.5% lên 5.2% — cân nhắc tái deposit?"

---

# Section 5: News (Stories S14, S15)

## TC-018: News RSS fetch
**Type:** Provider | **Story:** P3.9-S14

**Steps:**
1. Trigger `POST /admin/jobs/run?name=news_updater`
2. Query DB: `SELECT count(*) FROM news_articles WHERE fetched_at > NOW() - INTERVAL '5 minutes'`

**Expected Results:**
- Count > 0
- Articles có distinct URLs (dedup)
- `published_at` không null

---

## TC-019: News symbol tagging
**Type:** Critical | **Story:** P3.9-S15

**Steps:**
1. Insert test article: title "Hòa Phát công bố lợi nhuận Q2 vượt kỳ vọng"
2. Run `tag_news_with_symbols(article)`

**Expected Results:**
- `related_symbols` field updated với `["HPG"]`
- Không match nhầm symbols khác

---

## TC-020: Personalized news for Hà
**Type:** Happy | **Story:** P3.9-S15
**Persona:** Hà (holds VNM, HPG, VIC, FPT)

**Steps:**
1. Trigger Hà briefing render
2. Inspect news section

**Expected Results:**
- 3 news items
- Items có symbol match holdings của Hà được prioritize
- Mỗi item có summary 1 câu (LLM generated)
- Persona warm, conversational

---

## TC-021: News for BrandNew (no holdings)
**Type:** Corner | **Story:** P3.9-S15
**Persona:** BrandNew

**Steps:**
1. Trigger BrandNew briefing

**Expected Results:**
- News section show 3 general market news (không có holdings để filter)
- Hoặc skip section nếu rỗng (theo design)

---

# Section 6: Cache Layer (Story S2)

## TC-022: Cache hit returns cached value
**Type:** Cache | **Story:** P3.9-S2

**Steps:**
1. Fetch VNM lần 1: trigger cache write, ghi nhận `fetched_at`
2. Fetch VNM lần 2 trong vòng 5 phút

**Expected Results:**
- Lần 2 không gọi SSI (check log)
- `fetched_at` của response = `fetched_at` lần 1 (cùng quote object)
- Latency lần 2 < 50ms

---

## TC-023: Cache expiry
**Type:** Cache | **Story:** P3.9-S2

**Steps:**
1. Fetch BTC, ghi nhận thời gian
2. Đợi 2.5 phút (TTL = 2 phút cho crypto)
3. Fetch BTC lần 2

**Expected Results:**
- Lần 2 gọi CoinGecko (cache miss + write)
- `fetched_at` mới hơn lần 1

---

## TC-024: Stale-while-revalidate khi provider down
**Type:** Critical | **Story:** P3.9-S2

**Preconditions:** Cache có entry VNM (last_known), provider mock fail

**Steps:**
1. Wait cache TTL expire
2. Mock SSI và VNDIRECT đều fail
3. Fetch VNM

**Expected Results:**
- Response trả về stale data từ `last_known`
- Field `is_stale: true`
- Log warning: `"Returning stale data for VNM"`

---

## TC-025: Cache key namespace isolation
**Type:** Cache | **Story:** P3.9-S2

**Steps:**
1. Set `market_data:stock:VNM` = quote A
2. Set `session:user-123:VNM` = "unrelated"
3. Flush market_data namespace: `redis-cli --scan --pattern "market_data:*" | xargs redis-cli DEL`

**Expected Results:**
- `market_data:stock:VNM` deleted
- `session:user-123:VNM` vẫn còn

---

# Section 7: Wealth Valuation Integration (Story S9, S12)

## TC-026: Stock holding shows real-time price
**Type:** Happy | **Story:** P3.9-S9
**Persona:** Hà

**Steps:**
1. Hà gửi: "tài sản của tôi"
2. Bot trả response

**Expected Results:**
- Stock section show 4 holdings
- Mỗi holding có 2 prices: cost basis (giá mua) + current price
- P/L % calculated
- Format: "VNM: 200cp × 72,500 (mua 70k) = 14.5tr (+3.6%)"

---

## TC-027: Wealth fallback khi provider down
**Type:** Critical | **Story:** P3.9-S9

**Preconditions:** Mock all stock providers fail

**Steps:**
1. Hà gửi: "tài sản"

**Expected Results:**
- Response vẫn render (không error)
- Stocks dùng `user_input_price` (cost basis)
- Footer banner: "(Một số giá là dữ liệu cũ)"
- P/L % không hiển thị hoặc hiển thị "—"

---

## TC-028: Crypto holding shows real-time price
**Type:** Happy | **Story:** P3.9-S9
**Persona:** Phương

**Steps:**
1. Phương gửi: "crypto của tôi"

**Expected Results:**
- 3 holdings (BTC, ETH, SOL) hiển thị
- Mỗi holding: amount × current_price = total
- Total VND đúng (cross check với CoinGecko web)

---

## TC-029: Gold holding integration
**Type:** Happy | **Story:** P3.9-S12
**Persona:** Phương

**Steps:**
1. Phương gửi: "vàng của tôi"

**Expected Results:**
- "5 lượng × 78,500,000 = 392,500,000 VND"
- Source note: "Giá SJC cập nhật <time>"

---

# Section 8: Enhanced Briefing (Story S16)

## TC-030: Briefing — Persona Hà full render
**Type:** Happy | **Story:** P3.9-S16
**Persona:** Hà

**Steps:**
1. Trigger morning briefing cho Hà

**Expected Results:**
- 5 sections render đầy đủ:
  1. Tổng tài sản với change vs hôm qua
  2. Thị trường (VN-Index, Gold, BTC)
  3. Portfolio breakdown
  4. Top 3 news (relevant to Hà)
  5. Insights (max 2)
- Persona warm, gọi tên "Hà"
- No raw JSON or technical errors leaked
- Latency < 2s

---

## TC-031: Briefing — Persona BrandNew (empty portfolio)
**Type:** Corner | **Story:** P3.9-S16
**Persona:** BrandNew

**Steps:**
1. Trigger briefing

**Expected Results:**
- Portfolio section: "Bạn chưa có holdings nào" (gracefully)
- Market section vẫn render (VN-Index, Gold, BTC)
- News section: general market news
- Persona encouraging: "Hãy bắt đầu nhập tài sản đầu tiên"

---

## TC-032: Briefing — Persona Phương full data
**Type:** Happy | **Story:** P3.9-S16
**Persona:** Phương

**Steps:**
1. Trigger briefing

**Expected Results:**
- All sections render
- Portfolio breakdown: 5 categories (stocks, crypto, gold, BĐS, cash)
- Insights mention specific holdings (vd: "HPG tăng mạnh hôm nay")
- Total tài sản match wealth API

---

## TC-033: Briefing latency benchmark
**Type:** Performance | **Story:** P3.9-S16

**Preconditions:** Cache pre-warmed (jobs đã chạy trước đó)

**Steps:**
1. Trigger briefing 10 lần liên tiếp cho Phương
2. Measure latency mỗi lần

**Expected Results:**
- P50 < 1s
- P95 < 2s
- P99 < 3s
- No timeouts

---

## TC-034: Briefing với stale data banner
**Type:** Critical | **Story:** P3.9-S16

**Preconditions:** Mock 1 provider fail (gold)

**Steps:**
1. Wait gold cache expire
2. Trigger briefing

**Expected Results:**
- Briefing render bình thường
- Footer banner: "(Giá vàng là dữ liệu cũ từ Xh trước)"
- Other sections không bị ảnh hưởng

---

## TC-035: Briefing insights — bank rate suggestion
**Type:** Happy | **Story:** P3.9-S16
**Persona:** Phương (cash 500tr tại MB rate 4.8%)

**Preconditions:** Mock VCB rate hiện tại 5.5%

**Steps:**
1. Trigger briefing

**Expected Results:**
- Insights có entry: "Lãi suất VCB (5.5%) cao hơn MB (4.8%) — cân nhắc chuyển?"
- Insight không repeat nếu đã shown trong 7 ngày qua

---

# Section 9: Portfolio Analytics (Story S17)

## TC-036: YTD return calculation
**Type:** Happy | **Story:** P3.9-S17
**Persona:** Phương

**Preconditions:** `stock_historical_prices` table có entries cho 1/1/2026

**Steps:**
1. Query `GET /api/portfolio/ytd-return?user_id=phuong`

**Expected Results:**
- Response: `{available: true, return_pct: <number>, by_holding: [...]}`
- Tính đúng: `(current - start_year) / start_year * 100` cho mỗi stock
- Aggregate weighted by holding size

---

## TC-037: YTD return — missing historical data
**Type:** Corner | **Story:** P3.9-S17

**Preconditions:** Stock mới mua trong năm, không có giá 1/1

**Steps:**
1. Query YTD return

**Expected Results:**
- Response: `{available: false, reason: "no_historical_data"}` cho stock đó
- Aggregate skip stock này, vẫn tính cho stocks khác

---

## TC-038: Best/Worst performer
**Type:** Happy | **Story:** P3.9-S17
**Persona:** Phương

**Steps:**
1. Query best/worst performer hôm nay

**Expected Results:**
- Best: stock có `change_pct` cao nhất + tên + %
- Worst: stock có `change_pct` thấp nhất + tên + %
- Tie-break: alphabetical

---

## TC-039: Diversification score
**Type:** Happy | **Story:** P3.9-S17

**Steps:**
1. Compute score cho 3 personas

**Expected Results:**
- Hà (4 stocks + crypto + gold + cash): score 50-70 (Trung bình)
- Phương (5 asset types đa dạng): score 70-85 (Tốt)
- BrandNew (0 holdings): score 0 hoặc N/A

---

# Section 10: Price Alerts (Story S18)

## TC-040: Alert triggers on >5% movement
**Type:** Critical | **Story:** P3.9-S18
**Persona:** Hà (holds HPG)

**Preconditions:** `MARKET_DATA_ALERTS_ENABLED=true`

**Steps:**
1. Cache HPG = 25,000 (last_known 15min ago)
2. Mock new quote HPG = 26,500 (+6%)
3. Trigger stock_updater job

**Expected Results:**
- Hà nhận Telegram message
- Format: "HPG tăng 6.0% trong 15 phút qua (từ 25,000 → 26,500)"
- DB `price_alerts_log` có entry

---

## TC-041: Alert anti-spam — cooldown
**Type:** Critical | **Story:** P3.9-S18
**Persona:** Hà

**Preconditions:** Alert HPG vừa gửi 5 phút trước

**Steps:**
1. Mock thêm 1 movement HPG +7%
2. Trigger updater

**Expected Results:**
- Alert KHÔNG gửi (trong cooldown 30 phút)
- Log: "Alert skipped for HPG, in cooldown"

---

## TC-042: Alert max 3/day
**Type:** Critical | **Story:** P3.9-S18

**Preconditions:** Hà đã nhận 3 alerts hôm nay

**Steps:**
1. Trigger 4th alert (different symbol)

**Expected Results:**
- Alert KHÔNG gửi
- Log: "Daily alert limit reached for user"

---

## TC-043: Alert disabled by user
**Type:** Critical | **Story:** P3.9-S18
**Persona:** Hà với `notification_settings.price_alerts_enabled=false`

**Steps:**
1. Trigger alert condition

**Expected Results:**
- Alert KHÔNG gửi
- DB không có log entry

---

# Section 11: Agent Tool Integration (Story S19)

## TC-044: Agent — "VN-Index hôm nay?"
**Type:** Happy | **Story:** P3.9-S19

**Steps:**
1. User gửi: "VN-Index hôm nay thế nào?"

**Expected Results:**
- Bot dùng market_query tool
- Response có giá VN-Index real, % change
- KHÔNG có placeholder/stub data
- Latency < 2s

---

## TC-045: Agent — "BTC giá bao nhiêu?"
**Type:** Happy | **Story:** P3.9-S19

**Steps:**
1. User: "Bitcoin bao nhiêu rồi?"

**Expected Results:**
- Response: giá BTC VND + USD + change 24h
- Source note: "CoinGecko, cập nhật <time>"

---

## TC-046: Agent — "lãi suất Vietcombank 12 tháng?"
**Type:** Happy | **Story:** P3.9-S19

**Steps:**
1. User: "Lãi suất gửi 12 tháng VCB?"

**Expected Results:**
- Response: rate VCB 12m + last updated date
- Recommend cao hơn nếu có ngân hàng tốt hơn

---

## TC-047: Agent — Stub leakage check
**Type:** Regression | **Story:** P3.9-S19

**Steps:**
1. Test 10 market queries khác nhau qua agent

**Expected Results:**
- KHÔNG có response nào chứa: "stub", "placeholder", "test data", "hardcoded"
- All numbers reasonable (sanity check)

---

# Section 12: Job Reliability

## TC-048: Stock updater respects market hours
**Type:** Job | **Story:** P3.9-S7

**Steps:**
1. Verify cron schedule trong APScheduler
2. Check job logs từ tuần qua

**Expected Results:**
- Job runs entries chỉ trong khung 9:00-15:00 các ngày T2-T6
- KHÔNG run cuối tuần hoặc đêm

---

## TC-049: Crypto updater runs 24/7
**Type:** Job | **Story:** P3.9-S8

**Steps:**
1. Check job logs trong 48h

**Expected Results:**
- Job run đều mỗi 5 phút
- Có entries trong cuối tuần và ban đêm

---

## TC-050: Job metrics tracked
**Type:** Job | **Story:** P3.9-S7

**Steps:**
1. Query `GET /admin/jobs/health`

**Expected Results:**
- Response chứa cho mỗi job: `last_run_at`, `last_run_status`, `last_run_duration_ms`
- Status hợp lý (success / failed)
- Duration không quá lớn

---

## TC-051: Job no-op khi không có holdings
**Type:** Corner | **Story:** P3.9-S7

**Preconditions:** No user has any stock holdings

**Steps:**
1. Trigger stock_updater manual

**Expected Results:**
- Log: "stock_updater: no held symbols, skipping"
- Job complete < 100ms
- No API calls made

---

## TC-052: Provider health check job
**Type:** Job | **Story:** P3.9-S22 (admin alert path)

**Steps:**
1. Trigger `provider_health_check` job

**Expected Results:**
- Owner Telegram chat nhận daily summary
- Format: "Provider health: SSI X%, VNDIRECT Y%, ..."

---

# Section 13: Performance & Load

## TC-053: Cache hit rate after 1h
**Type:** Performance | **Story:** P3.9-S2

**Preconditions:** System running 1h+ với jobs active

**Steps:**
1. Query `GET /admin/cache/stats`

**Expected Results:**
- Hit rate > 80% cho stocks và crypto
- Hit rate > 95% cho gold (TTL dài hơn)

---

## TC-054: Concurrent briefing requests
**Type:** Performance | **Story:** P3.9-S16

**Steps:**
1. Trigger 10 briefings đồng thời (3 personas)

**Expected Results:**
- Tất cả complete < 3s
- No errors / timeouts
- DB connection pool không exhausted

---

## TC-055: Bank rates job duration
**Type:** Performance | **Story:** P3.9-S13

**Steps:**
1. Trigger bank_rates_updater

**Expected Results:**
- Total duration < 90s (target 60s, allow buffer)
- Each bank parser < 5s
- Failed banks không make job hang

---

# Section 14: Regression (Phase 3.5/3.6/3.7/3.8/3.8.5 still works)

## TC-056: Phase 3.5 intent classifier still works
**Type:** Regression

**Steps:**
1. Test 5 free-form queries: "tài sản của tôi có gì?", "tháng này tôi xài bao nhiêu?", v.v.

**Expected Results:**
- Intent classifier route correctly
- No regression vs Phase 3.5 baseline

---

## TC-057: Phase 3.7 agent tools all work
**Type:** Regression

**Steps:**
1. Test 5 tools (storytelling, advisory, query_goals, query_assets, market_query)

**Expected Results:**
- All tools respond correctly
- Streaming works
- market_query NOW uses real data (improvement, not regression)

---

## TC-058: Phase 3.8 wealth tracking unchanged
**Type:** Regression

**Steps:**
1. Test rental property income, multi-income streams, recurring transactions, cashflow forecast, goals CRUD

**Expected Results:**
- All features work identically to Phase 3.8

---

## TC-059: Phase 3.8.5 feedback + profile unchanged
**Type:** Regression

**Steps:**
1. Test /feedback command, profile view, edit display name, wealth level badge

**Expected Results:**
- All features work, no regression

---

## TC-060: Persona "Bé Tiền" warmth preserved
**Type:** Regression

**Steps:**
1. Read 5 briefings, 5 advisory responses, 5 query responses

**Expected Results:**
- Tone consistent với Phase 3.5+ standards
- No harsh / robotic / corporate language
- Vietnamese natural, not translated-feeling

---

# Section 15: Real User Trial (1-week soft launch dry run)

## TC-061: Day 1 — Owner self-test all flows
**Type:** Real Trial | **Story:** All

**Steps:**
1. Owner uses bot normally for 1 ngày
2. Trigger briefing morning
3. Add new asset
4. Query portfolio
5. Test alert (if condition met)

**Expected Results:**
- All works end-to-end
- No errors visible to user
- Numbers match expectations

---

## TC-062: Day 3 — Cross-validate prices with external apps
**Type:** Real Trial

**Steps:**
1. Open SSI iBoard app, note 5 stock prices at exact time T
2. Trigger briefing at time T
3. Compare numbers

**Expected Results:**
- Stock prices match ± 0.5% (allow for timing diff)
- Gold price match SJC web ± 0%
- BTC match CoinGecko web ± 0.1%

---

## TC-063: Day 7 — Health check report
**Type:** Real Trial

**Steps:**
1. Owner reviews owner alert channel for past 7 days
2. Check provider health summaries
3. Identify any parser breakage

**Expected Results:**
- > 95% uptime cho mỗi provider
- Bất kỳ ParserError nào đã được auto-fallback
- No user-facing errors logged

---

# Section 16: Security & Privacy

## TC-064: API keys not leaked in logs
**Type:** Security

**Steps:**
1. Search logs cho strings từ env vars (SSI_API_KEY, COINGECKO_PRO_KEY)

**Expected Results:**
- Zero matches
- Logs redact sensitive data

---

## TC-065: Internal admin endpoints require auth
**Type:** Security

**Steps:**
1. Try `GET /admin/market-data/test-fetch` without API key

**Expected Results:**
- HTTP 401 Unauthorized

---

## TC-066: User cannot query other users' holdings
**Type:** Security
**Persona:** Hà tries to access Phương's data

**Steps:**
1. Hà sends crafted query trying to reference user_id của Phương

**Expected Results:**
- Bot responds với data của Hà only
- Multi-tenancy isolation preserved

---

# Section 17: Edge Cases

## TC-067: Stock symbol case sensitivity
**Type:** Corner

**Steps:**
1. Query "vnm" (lowercase), "VNM" (upper), "Vnm" (mixed)

**Expected Results:**
- All return same result (normalized to upper internally)

---

## TC-068: Crypto symbol with special chars
**Type:** Corner

**Steps:**
1. Query "BTC ", " btc", "BTC."

**Expected Results:**
- Trim whitespace, ignore trailing punctuation
- Return BTC quote

---

## TC-069: Briefing during midnight (no recent data)
**Type:** Corner

**Steps:**
1. Trigger briefing at 02:00 AM

**Expected Results:**
- Stock data: stale banner OK (giờ giao dịch đóng)
- Crypto: fresh (24/7)
- Gold: stale banner OK (SJC chỉ update giờ làm việc)
- Briefing render OK với appropriate banners

---

## TC-070: Holiday handling
**Type:** Corner

**Preconditions:** Test on actual VN holiday (vd: Tết)

**Steps:**
1. Trigger briefing on holiday

**Expected Results:**
- Stock prices stale từ ngày làm việc cuối
- Briefing mention holiday context (optional)
- No errors

---

## TC-071: Massive portfolio (100+ holdings)
**Type:** Performance, Corner
**Persona:** Mock user với 100 stocks + 50 crypto

**Steps:**
1. Trigger wealth valuation

**Expected Results:**
- Complete < 5s
- No memory issues
- All holdings valued

---

## TC-072: Network unstable
**Type:** Critical, Corner

**Preconditions:** Simulate flaky network (50% packet loss)

**Steps:**
1. Run jobs for 30 minutes

**Expected Results:**
- Jobs retry với backoff
- Cache + last_known cứu nguy cho user-facing
- Some failures logged, không crash service

---

## TC-073: Decimal precision
**Type:** Critical

**Steps:**
1. Buy 100.5 cp HPG ở giá 25,123.45 VND
2. Compute total

**Expected Results:**
- Total = 2,524,906.725 VND
- Hiển thị làm tròn theo display rule (vd: "2.52tr")
- Internal Decimal precision preserved

---

## TC-074: Timezone correctness
**Type:** Critical

**Steps:**
1. Check `fetched_at` của quote tại thời điểm 14:30 VN time
2. Check briefing trigger time

**Expected Results:**
- All timestamps in `Asia/Ho_Chi_Minh` timezone
- Briefing morning trigger: 7:30 AM VN, không phải UTC

---

# Section 18: Observability

## TC-075: Provider error visible in dashboard
**Type:** Observability

**Steps:**
1. Cause provider error (mock)
2. Check `/admin/dashboard`

**Expected Results:**
- Error count incremented
- Latest error message visible
- Stack trace logged

---

## TC-076: Cache stats accessible
**Type:** Observability

**Steps:**
1. Query `/admin/cache/stats`

**Expected Results:**
- Hit rate %, miss count, total entries
- Per-asset-type breakdown

---

## TC-077: Job execution history
**Type:** Observability

**Steps:**
1. Query `/admin/jobs/history?limit=20`

**Expected Results:**
- Last 20 job runs với status, duration, errors

---

# Section 19: Documentation Verification

## TC-078: ADR documents key decisions
**Type:** Docs | **Story:** P3.9-S22

**Steps:**
1. Check ADR file exists: `docs/adr/0XX-market-data-providers.md`

**Expected Results:**
- File exists
- Documents primary/backup choices, scraping rationale, upgrade triggers

---

## TC-079: phase-status.yaml updated
**Type:** Docs | **Story:** P3.9-S22

**Steps:**
1. Read `docs/current/phase-status.yaml`

**Expected Results:**
- Phase 3.9 status `done`
- Phase 4A status `current` or `next`

---

## TC-080: CLAUDE.md updated
**Type:** Docs | **Story:** P3.9-S22

**Steps:**
1. Read `CLAUDE.md`

**Expected Results:**
- Phase 3.9 section reflects done status
- Test count updated

---

# Section 20: Smoke Test (Pre-Release Sanity)

## TC-081: Owner end-to-end manual smoke
**Type:** Critical
**Persona:** Owner (real account)

**Steps:**
1. Open Telegram, message bot "/briefing"
2. Verify all sections render
3. Send "tài sản"
4. Send "VN-Index"
5. Send "vàng SJC"
6. Send "lãi suất tốt nhất"

**Expected Results:**
- All commands respond < 3s
- Numbers reasonable
- No errors visible to user

---

## TC-082: All 4 personas baseline
**Type:** Critical

**Steps:**
1. Run briefing cho 4 personas (Hà, Phương, Minh, BrandNew)

**Expected Results:**
- Hà briefing có news về VNM/HPG
- Phương briefing có metrics đa dạng
- Minh briefing với 15+ stocks không lag
- BrandNew briefing graceful empty state

---

## TC-083: Database integrity post-phase
**Type:** Critical

**Steps:**
1. Query: `SELECT COUNT(*) FROM stock_holdings WHERE current_price IS NOT NULL`
2. Query: `SELECT COUNT(*) FROM news_articles WHERE published_at > NOW() - INTERVAL '24 hours'`
3. Query: `SELECT COUNT(*) FROM bank_rates WHERE snapshot_date = CURRENT_DATE`

**Expected Results:**
- Stock holdings có current_price
- News articles populated trong 24h qua
- Bank rates có data cho ngày hiện tại (nếu là sau thứ 2)

---

## TC-084: All scheduled jobs running
**Type:** Critical

**Steps:**
1. Check `/admin/jobs/health` for ALL jobs

**Expected Results:**
- Tất cả 6 jobs có `last_run_status: success` trong khung thời gian phù hợp
- No job stuck > 24h without run

---

## TC-085: Feature flags rollout state
**Type:** Critical

**Steps:**
1. Check config: feature flags

**Expected Results:**
- `MARKET_DATA_USE_REAL_STOCKS=true`
- `MARKET_DATA_USE_REAL_GOLD=true`
- `MARKET_DATA_NEWS_ENABLED=true`
- `MARKET_DATA_ALERTS_ENABLED=true` (if cuối tuần 3)

---

## TC-086: Cost monitoring
**Type:** Critical

**Steps:**
1. Check LLM cost dashboard cho 7 ngày qua

**Expected Results:**
- News summarization total cost < $1/tuần (cho test users)
- Cost projection cho soft launch reasonable

---

## TC-087: Owner alert channel functioning
**Type:** Critical

**Steps:**
1. Force a parser error
2. Wait

**Expected Results:**
- Owner Telegram chat nhận alert trong vòng 5 phút

---

## TC-088: Final sign-off checklist
**Type:** Sign-off

**Checklist (all must be ✅):**
- [ ] All Story acceptance criteria met
- [ ] All test sections (1-19) executed, > 90% pass
- [ ] No critical (P0) bugs open
- [ ] Owner has tested for 7 days
- [ ] Documentation updated
- [ ] phase-status.yaml: 3.9 → done

---

# Test Execution Tracking Template

Recommend dùng spreadsheet hoặc Notion table:

| TC# | Title | Story | Status | Run Date | Tester | Notes |
|---|---|---|---|---|---|---|
| TC-001 | SSI happy path | S4 | ✅ | | | |
| TC-002 | SSI invalid symbol | S4 | ⚠️ | | | Returns 404 thay vì structured error |
| ... | | | | | | |

**Total: 88 cases**

---

# Risk Areas to Pay Extra Attention

1. **Section 4 (Bank rates)** — 20 parsers, expect 1-2 to fail initially
2. **Section 3 (Gold scraping)** — fragile, snapshot tests critical
3. **Section 10 (Alerts)** — anti-spam logic must be airtight
4. **Section 6 (Cache)** — stale-while-revalidate is subtle, test thoroughly
5. **Section 8 (Briefing)** — user-facing, persona consistency matters

---

**Phase 3.9 testing complete = ready for soft launch June 2026. 💚📊**
