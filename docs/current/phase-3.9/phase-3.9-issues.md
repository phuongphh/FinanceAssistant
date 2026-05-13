# Phase 3.9 — GitHub Issues

> **Reference:** [phase-3.9-detailed.md](./phase-3.9-detailed.md)
> **Structure:** Epic-as-parent / Story-as-child (consistent với Phase 3.5, 3.7, 3.8.5)
> **Total:** 5 Epics, 22 Stories, ~3 tuần work
> **Labels:** `phase-3.9`, `market-data`, plus per-Epic labels

---

## Phase Overview

Phase 3.9 thay thế stub market data từ Phase 3.7 bằng integration thật với SSI/VNDIRECT (stocks), CoinGecko (crypto), SJC/PNJ (gold), 20 ngân hàng (lãi suất), RSS feeds (news). Sau phase này, morning briefing và portfolio valuation hiển thị số liệu real-time, unlock soft launch tháng 6.

**Critical path:** Epic 1 (foundation) → Epic 2 (stock+crypto) song song với Epic 1, Epic 3 (gold+bank+news) → Epic 4 (briefing+analytics+alerts) → Epic 5 (testing + polish).

---

# Epic 1: Foundation & Provider Abstraction

**Label:** `epic`, `phase-3.9`, `foundation`
**Estimate:** 2-3 ngày (~Day 1-3)
**Goal:** Setup module structure, base classes, cache layer, error handling — nền móng cho mọi provider.

**Stories:** S1, S2, S3

---

## [Story] P3.9-S1: Module skeleton + BaseProvider abstract class

**Labels:** `story`, `phase-3.9`, `foundation`
**Parent:** Epic 1
**Estimate:** 0.5 ngày

### Description
Setup folder structure `app/market_data/` và define interface chung cho mọi provider để các Story sau implement theo.

### Acceptance Criteria
- [ ] Folder `app/market_data/` tồn tại với subfolders: `providers/`, `cache/`, `jobs/`, `analytics/`
- [ ] `app/market_data/base.py` chứa abstract class `BaseProvider` với 3 abstract methods: `fetch_quote`, `fetch_batch`, `asset_type`
- [ ] `app/market_data/normalizer.py` chứa dataclass `PriceQuote` với fields: `symbol`, `price (Decimal)`, `currency`, `asset_type`, `fetched_at`, `source`, `metadata`
- [ ] `app/market_data/exceptions.py` chứa exception hierarchy: `MarketDataError`, `ProviderUnavailable`, `RateLimitError`, `ParserError`, `SymbolNotFound`, `StaleDataWarning`
- [ ] Unit tests cho `PriceQuote` serialization (`to_json`, `from_json`)
- [ ] Type hints đầy đủ, mypy clean

### Technical Notes
- `Decimal` không phải `float` — money rule
- `to_json/from_json` để cache vào Redis (Redis chỉ lưu string)

### Dependencies
None.

---

## [Story] P3.9-S2: Redis price cache layer

**Labels:** `story`, `phase-3.9`, `foundation`
**Parent:** Epic 1
**Estimate:** 1 ngày

### Description
Build cache wrapper với TTL strategy theo asset type, cache-aside pattern, stale-while-revalidate fallback.

### Acceptance Criteria
- [ ] `app/market_data/cache/price_cache.py` với class `PriceCache`
- [ ] Methods: `get(key) → Optional[PriceQuote]`, `set(quote)`, `set_last_known(quote)`, `get_last_known(symbol)`, `flush_asset_type(asset_type)`
- [ ] TTL config map: stock=300s, crypto=120s, gold=3600s, bank_rate=604800s, news=1800s
- [ ] Key naming convention: `market_data:{asset_type}:{symbol}` cho cache, `market_data:{asset_type}:{symbol}:last_known` cho backup (no TTL)
- [ ] `get` trả về `None` nếu key không tồn tại hoặc đã expire
- [ ] `set_last_known` luôn ghi đè (last write wins)
- [ ] Unit tests: TTL expiry behavior, last_known persistence, key naming

### Technical Notes
- Dùng `redis.asyncio.Redis` (async client)
- Test với `fakeredis` library hoặc testcontainers Redis

### Dependencies
- S1 (cần `PriceQuote`)

---

## [Story] P3.9-S3: Provider dispatcher + circuit breaker

**Labels:** `story`, `phase-3.9`, `foundation`
**Parent:** Epic 1
**Estimate:** 1 ngày

### Description
Implement fallback logic generic (try primary → fallback to secondary) và simple circuit breaker để tránh hammer provider đang down.

### Acceptance Criteria
- [ ] `app/market_data/providers/base_dispatcher.py` với class `Dispatcher(primary, secondary, timeout=3.0)`
- [ ] Method `fetch_quote(symbol)`: try primary với timeout, catch `(TimeoutError, ProviderUnavailable, RateLimitError)`, fallback secondary
- [ ] Circuit breaker: count consecutive failures per provider trong Redis (key `market_data:health:{provider}:failures`)
- [ ] Nếu failures >= 5 trong 60s → "open circuit" trong 5 phút (Redis key `market_data:health:{provider}:open_until`)
- [ ] Open circuit → skip primary, đi thẳng secondary
- [ ] Sau 5 phút → "half-open": cho 1 request thử, success → reset, fail → mở lại 5 phút
- [ ] Unit tests cho cả 3 trạng thái: closed, open, half-open

### Technical Notes
- Không cần lib bên ngoài, implement bằng Redis counter
- Log mọi state transition: `"Circuit OPEN for ssi"`, `"Circuit HALF-OPEN for ssi, testing"`, `"Circuit CLOSED for ssi"`

### Dependencies
- S2 (cần Redis)

---

# Epic 2: Stock + Crypto Providers (Tuần 1)

**Label:** `epic`, `phase-3.9`, `provider`
**Estimate:** ~5 ngày (Day 4-8)
**Goal:** Real stock + crypto data flowing into wealth valuation.

**Stories:** S4, S5, S6, S7, S8, S9

---

## [Story] P3.9-S4: SSI iBoard stock provider (primary)

**Labels:** `story`, `phase-3.9`, `provider`, `stocks`
**Parent:** Epic 2
**Estimate:** 1 ngày

### Description
Implement SSI iBoard API client cho real-time stock quotes.

### Acceptance Criteria
- [ ] `app/market_data/providers/stock_ssi.py` với class `SSIStockProvider(BaseProvider)`
- [ ] `fetch_quote(symbol)` gọi SSI iBoard endpoint, parse response → `PriceQuote`
- [ ] `fetch_batch(symbols)` dùng SSI batch endpoint nếu có, hoặc concurrent calls với `asyncio.gather`
- [ ] `metadata` chứa: `volume`, `change_pct`, `high`, `low`, `open`
- [ ] Error handling: HTTP 4xx → `SymbolNotFound` hoặc `ProviderUnavailable`, HTTP 5xx → `ProviderUnavailable`, HTTP 429 → `RateLimitError`
- [ ] Timeout configurable (default 3s)
- [ ] Unit tests với mocked HTTP responses (4 cases: success, 404, 500, 429)
- [ ] Integration test với 1 symbol thật (manual run, không trong CI)

### Technical Notes
- Dùng `httpx.AsyncClient`
- Endpoint exact path TBD — confirm trong implementation
- Một số stocks có thể không có data trong SSI (vd: UPCOM ít phổ biến) → catch và log

### Dependencies
- S1, S2

---

## [Story] P3.9-S5: VNDIRECT stock provider (backup)

**Labels:** `story`, `phase-3.9`, `provider`, `stocks`
**Parent:** Epic 2
**Estimate:** 0.5 ngày

### Description
Implement VNDIRECT API client làm backup khi SSI unavailable.

### Acceptance Criteria
- [ ] `app/market_data/providers/stock_vndirect.py` tương tự SSI
- [ ] Schema response của VNDIRECT khác SSI → normalize về cùng `PriceQuote`
- [ ] `stock_dispatcher.py` dùng `Dispatcher(SSI, VNDIRECT, timeout=3.0)`
- [ ] Unit tests cho VNDIRECT parser
- [ ] Integration test: kill SSI (mock fail) → verify VNDIRECT được gọi

### Dependencies
- S3, S4

---

## [Story] P3.9-S6: CoinGecko crypto provider

**Labels:** `story`, `phase-3.9`, `provider`, `crypto`
**Parent:** Epic 2
**Estimate:** 0.5 ngày

### Description
CoinGecko free tier integration cho crypto prices.

### Acceptance Criteria
- [ ] `app/market_data/providers/crypto_coingecko.py`
- [ ] `coingecko_symbols.py` mapping table: ticker (BTC, ETH, SOL, ...) → coingecko_id (bitcoin, ethereum, solana, ...). Min 20 cryptos phổ biến.
- [ ] `fetch_quote(symbol="BTC")` lookup mapping → call API với coin_id → return `PriceQuote(currency="VND", price=...)`
- [ ] `fetch_batch` dùng comma-separated IDs trong 1 request (CoinGecko hỗ trợ)
- [ ] Rate limit handling: nếu 429 → exponential backoff (1s, 2s, 4s) max 3 retries
- [ ] Symbol không có trong mapping → `SymbolNotFound`
- [ ] Unit tests

### Technical Notes
- CoinGecko free: 10-30 req/min — mỗi batch fetch 1 request lấy nhiều coins → giảm risk
- Endpoint: `GET /simple/price?ids={coin_ids}&vs_currencies=usd,vnd`

### Dependencies
- S1, S2

---

## [Story] P3.9-S7: Stock price auto-updater (cron job)

**Labels:** `story`, `phase-3.9`, `job`, `stocks`
**Parent:** Epic 2
**Estimate:** 0.5 ngày

### Description
Background job pre-warm cache cho mọi stock user đang hold, chạy 15 phút/lần trong giờ giao dịch.

### Acceptance Criteria
- [ ] `app/market_data/jobs/stock_updater.py` function `update_all_held_stocks()`
- [ ] Logic: query distinct symbols từ `stock_holdings` table → batch fetch via dispatcher → write to cache (both regular + last_known)
- [ ] Schedule: cron `*/15 * * * *` chỉ trong khung 9:00-15:00, T2-T6 (HOSE trading hours)
- [ ] Register vào APScheduler trong `app/scheduler.py`
- [ ] Metrics logged: `symbols_attempted`, `symbols_succeeded`, `duration_ms`
- [ ] No-op nếu không có user nào hold stock
- [ ] Unit test với mocked DB + dispatcher

### Dependencies
- S5, S2

---

## [Story] P3.9-S8: Crypto price auto-updater

**Labels:** `story`, `phase-3.9`, `job`, `crypto`
**Parent:** Epic 2
**Estimate:** 0.25 ngày

### Description
Tương tự S7 nhưng cho crypto, schedule mỗi 5 phút 24/7.

### Acceptance Criteria
- [ ] `app/market_data/jobs/crypto_updater.py`
- [ ] Schedule: interval 5 phút
- [ ] Tương tự logic S7

### Dependencies
- S6, S2

---

## [Story] P3.9-S9: Wealth valuation integration (stocks + crypto)

**Labels:** `story`, `phase-3.9`, `wealth`
**Parent:** Epic 2
**Estimate:** 1 ngày

### Description
Switch wealth valuation từ user_input_price sang real market price (cache-first).

### Acceptance Criteria
- [ ] `app/wealth/valuation/stock.py` updated: `value_stock_holding(holding)` gọi `market_data.get_stock_quote(holding.symbol)` thay vì `holding.user_input_price`
- [ ] Giữ nguyên field `user_input_price` trong DB (đây là cost basis cho P/L calculation)
- [ ] Add field `current_price` (computed at read time, không lưu DB)
- [ ] Add field `pnl_pct` = `(current_price - user_input_price) / user_input_price * 100`
- [ ] Tương tự cho `app/wealth/valuation/crypto.py`
- [ ] Fallback behavior: nếu market_data raise `ProviderUnavailable` → log warning, return `user_input_price` với flag `is_stale=True`
- [ ] All Phase 3.7 + 3.8 tests vẫn pass (regression check)
- [ ] Add 5 new tests cho fallback + P/L calculation

### Technical Notes
- Đây là **schema additive change** — không break existing API contracts
- Briefing và portfolio queries downstream sẽ tự động dùng giá mới

### Dependencies
- S7, S8

---

# Epic 3: Gold + Bank Rates + News (Tuần 2)

**Label:** `epic`, `phase-3.9`, `provider`
**Estimate:** ~5 ngày (Day 9-13)
**Goal:** Complete data sources for full briefing.

**Stories:** S10, S11, S12, S13, S14, S15

---

## [Story] P3.9-S10: SJC gold scraper (primary)

**Labels:** `story`, `phase-3.9`, `provider`, `gold`, `scraper`
**Parent:** Epic 3
**Estimate:** 0.75 ngày

### Description
Scrape SJC website cho giá vàng SJC (loại phổ biến nhất ở VN).

### Acceptance Criteria
- [ ] `app/market_data/providers/gold_sjc.py` với class `SJCGoldProvider(BaseProvider)`
- [ ] `fetch_quote(symbol="SJC_GOLD" | "RING_24K")` parse HTML từ SJC textContent endpoint
- [ ] Fixture HTML lưu trong `tests/fixtures/sjc_sample.html`, parser test pass với fixture
- [ ] Parse được: giá mua, giá bán, thời gian update của SJC
- [ ] `metadata` chứa `buy_price`, `sell_price`, `sjc_updated_at`
- [ ] `price` field = giá bán (giá user thực tế phải trả)
- [ ] `ParserError` nếu HTML structure không match expected (vd: thiếu table)

### Technical Notes
- SJC update 3 lần/ngày: ~9h, ~13h, ~16h
- Có thể test trong giờ làm việc tốt nhất
- Backup fallback: PNJ (S11)

### Dependencies
- S1

---

## [Story] P3.9-S11: PNJ gold scraper (backup)

**Labels:** `story`, `phase-3.9`, `provider`, `gold`, `scraper`
**Parent:** Epic 3
**Estimate:** 0.5 ngày

### Description
PNJ scraper backup cho khi SJC parser break.

### Acceptance Criteria
- [ ] `app/market_data/providers/gold_pnj.py`
- [ ] `gold_dispatcher.py` dùng `Dispatcher(SJC, PNJ, timeout=5.0)`
- [ ] Fixture HTML PNJ
- [ ] Unit + integration tests

### Dependencies
- S3, S10

---

## [Story] P3.9-S12: Gold price auto-updater + wealth integration

**Labels:** `story`, `phase-3.9`, `job`, `wealth`, `gold`
**Parent:** Epic 3
**Estimate:** 0.5 ngày

### Description
Cron 3 lần/ngày + update `wealth/valuation/gold.py`.

### Acceptance Criteria
- [ ] `app/market_data/jobs/gold_updater.py` schedule: cron `0 9,13,16 * * *`
- [ ] `app/wealth/valuation/gold.py` updated tương tự S9
- [ ] Test fallback: SJC fail → wealth valuation vẫn work qua PNJ
- [ ] Test ultimate fallback: cả 2 fail → return user_input_price + stale flag

### Dependencies
- S11

---

## [Story] P3.9-S13: Bank rates scraper (top 20 banks)

**Labels:** `story`, `phase-3.9`, `provider`, `bank-rates`, `scraper`
**Parent:** Epic 3
**Estimate:** 2 ngày (lớn nhất trong phase — 20 parsers)

### Description
Scrape lãi suất tiết kiệm từ 20 ngân hàng phổ biến nhất.

### Acceptance Criteria
- [ ] `app/market_data/providers/bank_parsers/` folder chứa 20 file: `vcb.py`, `bidv.py`, `agribank.py`, ...
- [ ] Mỗi parser implement `parse_rates(html: str) -> list[BankRate]`
- [ ] `bank_rates_scraper.py` orchestrator: fetch HTML từng bank, gọi parser, gom kết quả
- [ ] Schema `BankRate`: `bank_code`, `bank_name`, `tenor_months` (1, 3, 6, 12, 24), `rate_pct`, `deposit_type` (regular/online), `notes`
- [ ] DB migration: tạo table `bank_rates` (xem section 15.3 của detailed.md)
- [ ] Mỗi bank có fixture HTML test
- [ ] Banks ưu tiên (làm trước, MUST work): VCB, BIDV, Agribank, Vietinbank, Techcombank, MBBank, ACB, VPBank
- [ ] Banks tier 2 (làm sau, OK nếu fail 1-2): còn lại
- [ ] Skip mechanism: bank nào fail thì log + skip, không break job
- [ ] Job updater (S13b sub-task): schedule weekly Monday 6am

### Technical Notes
- Đây là Story lớn, có thể tách thành sub-tasks: 8 banks tier 1 (1 ngày) + 12 banks tier 2 (1 ngày)
- Một số ngân hàng dùng JS render → có thể cần Playwright/Selenium thay BeautifulSoup → check trong implementation

### Dependencies
- S1, S2

---

## [Story] P3.9-S14: News RSS feed integration

**Labels:** `story`, `phase-3.9`, `provider`, `news`
**Parent:** Epic 3
**Estimate:** 0.5 ngày

### Description
Fetch + parse RSS feeds, lưu articles vào DB.

### Acceptance Criteria
- [ ] `app/market_data/providers/news_rss.py` dùng `feedparser`
- [ ] Sources: cafef.vn (chứng khoán), vnexpress kinh doanh, ndh.vn (optional)
- [ ] Cron hourly: fetch all feeds → dedupe by URL → insert vào `news_articles` table
- [ ] DB migration: table `news_articles` (xem detailed.md section 15.3)
- [ ] Field `related_symbols` initially empty array — populated trong S15
- [ ] Test với fixture XML

### Dependencies
- S1

---

## [Story] P3.9-S15: News LLM summarization tied to holdings

**Labels:** `story`, `phase-3.9`, `news`, `llm`
**Parent:** Epic 3
**Estimate:** 0.75 ngày

### Description
Tag news với related stock symbols + generate personalized summary cho user.

### Acceptance Criteria
- [ ] `app/market_data/analytics/news_relevance.py` function `tag_news_with_symbols(article)`:
  - Pattern match titles + first 200 chars vs stock ticker dictionary (~700 HOSE/HNX symbols)
  - Update `news_articles.related_symbols` field
- [ ] Function `get_relevant_news(user_id, limit=3)`:
  - Get user's holdings (stocks + crypto)
  - Query news với `related_symbols && user_symbols` (PostgreSQL array overlap)
  - Sort: news mention user holdings > general market > others, then by `published_at DESC`
- [ ] Function `summarize_for_user(user_id) -> list[str]`:
  - Get top 3 relevant news
  - 1 LLM call (DeepSeek) với prompt format đã define trong detailed.md section 3.6
  - Output: list 3 sentence summaries (max 1 sentence each)
- [ ] Cost test: P95 LLM call < $0.0015 (~500 tokens)
- [ ] Manual test: 3 personas (Hà, Phương, Minh) → summary đúng holdings

### Dependencies
- S14

---

# Epic 4: Enhanced Briefing + Analytics + Alerts (Tuần 3)

**Label:** `epic`, `phase-3.9`, `briefing`
**Estimate:** ~5 ngày (Day 14-18)
**Goal:** User-facing improvements that make Phase 3.9 visible and valuable.

**Stories:** S16, S17, S18, S19

---

## [Story] P3.9-S16: Morning briefing enrichment

**Labels:** `story`, `phase-3.9`, `briefing`
**Parent:** Epic 4
**Estimate:** 1.5 ngày

### Description
Update briefing template và renderer để hiển thị real market data + portfolio performance + news.

### Acceptance Criteria
- [ ] `content/briefing.yaml` có template mới với 5 sections (xem detailed.md section 7.2):
  - Tổng tài sản + change vs hôm qua/tuần
  - Thị trường sáng nay (VN-Index, Gold ref, BTC ref)
  - Portfolio breakdown (% allocation per asset type, today's change)
  - Top 3 news cho user
  - Insights (rule-based, max 2)
- [ ] `app/briefing/morning_briefing.py` updated:
  - Parallel fetch: portfolio, market overview, metrics, news, insights (use `asyncio.gather`)
  - Total render time < 2s P95
- [ ] Insights generator (rule-based, không LLM):
  - Stock tăng > 5% hôm nay → "Stock X tăng mạnh, có thể chốt lời 1 phần?"
  - Bank rate user đang gửi thấp hơn rate VCB > 0.5% → "Cân nhắc chuyển ngân hàng"
- [ ] Stale data banner: nếu bất kỳ price nào `is_stale=True` → footer "(Một số giá là dữ liệu cũ)"
- [ ] All existing briefing tests pass + 8 new tests
- [ ] Manual test: 4 personas → briefing render đúng + persona warm/empathetic

### Dependencies
- S9, S12, S15

---

## [Story] P3.9-S17: Portfolio analytics

**Labels:** `story`, `phase-3.9`, `analytics`
**Parent:** Epic 4
**Estimate:** 1 ngày

### Description
Compute YTD return, best/worst performer, diversification score.

### Acceptance Criteria
- [ ] `app/market_data/analytics/portfolio_metrics.py`
- [ ] Function `compute_ytd_return(user_id) -> dict`:
  - Fetch historical price từ `stock_historical_prices` table cho ngày 1/1/{year}
  - Nếu chưa có → fetch từ SSI historical endpoint, store vào DB (one-time job đầu năm)
  - Return: `{available, return_pct, absolute, by_holding: [...]}`
- [ ] Function `get_best_worst_performer(user_id) -> tuple[Holding, Holding]`
- [ ] Function `compute_diversification_score(portfolio) -> int (0-100)`:
  - Logic theo detailed.md section 8.3
  - Output: số 0-100 + label categorical ("Tốt"/"Trung bình"/"Yếu")
- [ ] Job `historical_price_seeder.py` chạy 1 lần đầu năm (cron `0 7 1 1 *`) hoặc on-demand
- [ ] DB migration: `stock_historical_prices` table
- [ ] Unit tests cho 3 functions
- [ ] Briefing template (S16) reference các metric này

### Dependencies
- S9, S16

---

## [Story] P3.9-S18: Price movement alerts

**Labels:** `story`, `phase-3.9`, `alerts`
**Parent:** Epic 4
**Estimate:** 1 ngày

### Description
Send Telegram alert khi stock user hold biến động > 5% trong 15 phút.

### Acceptance Criteria
- [ ] `app/market_data/analytics/alerts.py` function `check_movements(quotes)`:
  - Compare new quote vs `last_known` 15 phút trước
  - If `abs(change_pct) >= 5.0` → trigger alert
- [ ] Alert message format Vietnamese, friendly persona "Bé Tiền"
- [ ] Anti-spam:
  - Max 3 alerts/user/ngày
  - Cooldown 30 phút cho cùng symbol
  - Severity: `info` (5-7%), `warning` (7-10%), `critical` (>10%)
- [ ] DB log table: `price_alerts_log` (xem detailed.md section 15.3)
- [ ] User setting: `notification_settings.price_alerts_enabled` (default True)
- [ ] Trigger từ S7 stock updater
- [ ] Feature flag `MARKET_DATA_ALERTS_ENABLED` (off by default, on cuối tuần 3)
- [ ] Manual test: simulate price spike → verify alert sent

### Dependencies
- S7

---

## [Story] P3.9-S19: Replace Phase 3.7 stubs in agent tools

**Labels:** `story`, `phase-3.9`, `agent`
**Parent:** Epic 4
**Estimate:** 0.5 ngày

### Description
Update agent tools (Phase 3.7) để dùng real data thay vì stub.

### Acceptance Criteria
- [ ] `app/agent/tools/market_query.py` updated: gọi `market_data.get_*` functions
- [ ] Tool description (cho LLM) updated: bỏ "stub data" warning
- [ ] All Phase 3.7 agent tests pass
- [ ] 5 example queries test (manual): "VN-Index hôm nay?", "BTC giá bao nhiêu?", "vàng SJC?", "lãi suất Vietcombank?", "tin gì về HPG?"
- [ ] Performance: tool call latency P95 < 500ms (cache hit)

### Dependencies
- S9, S12, S13, S15

---

# Epic 5: Testing & Polish

**Label:** `epic`, `phase-3.9`, `testing`
**Estimate:** ~2 ngày (Day 19-20)
**Goal:** Quality gate before declaring phase done.

**Stories:** S20, S21, S22

---

## [Story] P3.9-S20: Integration tests end-to-end

**Labels:** `story`, `phase-3.9`, `testing`
**Parent:** Epic 5
**Estimate:** 1 ngày

### Description
End-to-end tests cover toàn bộ flow: provider → cache → wealth → briefing.

### Acceptance Criteria
- [ ] Test `test_briefing_full_flow.py`: setup user với 3 stocks + 1 crypto + 1 gold + cash → trigger briefing render → assert all sections present + numbers correct
- [ ] Test `test_provider_fallback.py`: mock SSI fail → verify VNDIRECT used → wealth valuation correct
- [ ] Test `test_circuit_breaker.py`: 5 consecutive failures → verify circuit opens → after 5min → half-open
- [ ] Test `test_stale_data_flow.py`: provider down → verify stale data shown with banner
- [ ] All tests pass in CI

### Dependencies
- All Stories from Epic 1-4

---

## [Story] P3.9-S21: Performance benchmarks + cache hit rate verification

**Labels:** `story`, `phase-3.9`, `testing`, `performance`
**Parent:** Epic 5
**Estimate:** 0.5 ngày

### Description
Benchmark key performance paths, verify cache effectiveness.

### Acceptance Criteria
- [ ] Benchmark script `scripts/bench_phase_3_9.py`:
  - Briefing render P50/P95/P99 (target: P95 < 2s)
  - Cache hit rate after 1h of jobs running (target: > 80%)
  - Bank rates job total duration (target: < 60s for 20 banks)
- [ ] Run benchmark, write results to `docs/current/phase-3.9-benchmark.md`
- [ ] Identify any regressions vs Phase 3.8 baseline

### Dependencies
- All Stories from Epic 1-4

---

## [Story] P3.9-S22: Documentation + ADR + phase-status update

**Labels:** `story`, `phase-3.9`, `docs`
**Parent:** Epic 5
**Estimate:** 0.5 ngày

### Description
Final docs, ADR cho key decisions, update phase status to done.

### Acceptance Criteria
- [ ] ADR file `docs/adr/0XX-market-data-providers.md` documenting:
  - Why SSI primary, VNDIRECT backup (cost? reliability? coverage?)
  - Why CoinGecko free tier (rate limit acceptable for current scale)
  - Why scraping (no PNJ/SJC API)
  - When to upgrade to paid tier (decision triggers)
- [ ] Update `CLAUDE.md` Phase 3.9 section: status `current → done`, summary line
- [ ] Update `docs/current/phase-status.yaml`: 3.9 status `done`, add 4A as `next`
- [ ] Update `README.md` if any user-facing changes
- [ ] Archive Phase 3.9 docs to `docs/archive/phase-3.9/` after ship (optional)

### Dependencies
- S20, S21

---

# Implementation Order Suggestion

```
Day 1-3   (Epic 1)         [S1] [S2] [S3]
Day 4-5   (Epic 2 stocks)  [S4] [S5]
Day 6     (Epic 2 crypto)  [S6]
Day 7     (Epic 2 jobs)    [S7] [S8]
Day 8     (Epic 2 wealth)  [S9]
Day 9     (Epic 3 SJC)     [S10]
Day 10    (Epic 3 PNJ+gold)[S11] [S12]
Day 11-12 (Epic 3 banks)   [S13]
Day 13    (Epic 3 news)    [S14] [S15]
Day 14-15 (Epic 4 brief)   [S16]
Day 16    (Epic 4 analyt)  [S17]
Day 17    (Epic 4 alerts)  [S18]
Day 18    (Epic 4 agent)   [S19]
Day 19    (Epic 5 tests)   [S20]
Day 20    (Epic 5 polish)  [S21] [S22]
```

**Buffer:** ~1 ngày trong tổng 21 days available — dùng cho debug provider quirks không lường trước.

---

# Common Pitfalls

1. **Decimal vs Float** — money rule, đặc biệt khi parse JSON từ providers (luôn cast về Decimal)
2. **Timezone** — VN giờ giao dịch là Asia/Ho_Chi_Minh, đừng để cron chạy theo UTC
3. **Provider response schema drift** — luôn validate với Pydantic, không trust HTML/JSON structure
4. **Cache key collision** — uppercase/lowercase symbols, normalize before key generation
5. **Rate limit cascading** — job chạy đồng thời với user query → cache aggressive cứu mạng
6. **Bank rate scraping** — 1-2 banks chắc chắn sẽ dùng JS render hoặc CAPTCHA, plan B sẵn (skip + log)
7. **Stale data UX** — nếu briefing toàn dữ liệu stale → user mất tin tưởng. Cần banner rõ ràng.

---

**Phase 3.9 = real data flowing. Foundation cho Phase 4 Twin có ý nghĩa. 💚📈**
