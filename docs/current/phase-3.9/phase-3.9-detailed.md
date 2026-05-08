# Phase 3.9 — Market Data Real

> **Status:** Planning → Ready for implementation
> **Duration:** ~3 tuần (15 working days, có buffer 2 ngày)
> **Target ship:** Mid-Late June 2026 (trước soft launch)
> **Predecessor:** Phase 3.8.5 (Feedback + Profile + Wealth Badge) — DONE
> **Successor:** Phase 4A (Financial Twin Conservative MVP)

---

## 1. Mục tiêu & Bối cảnh

### Vấn đề hiện tại (sau Phase 3.7 + 3.8 + 3.8.5)

Phase 3.7 đã build agent architecture với 5 tools, trong đó có **market data tool**. Nhưng tool này hiện đang trả về **stub data (giá giả)** — vì lúc đó focus là agent reasoning, không phải data integration.

Cụ thể, các điểm đang dùng stub:
- `stock_provider` — trả về giá random hoặc hardcode
- `crypto_provider` — trả về giá hardcode
- `gold_provider` — chưa tồn tại
- `bank_rates_provider` — chưa tồn tại
- `news_provider` — chưa tồn tại
- Morning briefing — render placeholder thay vì real numbers
- Portfolio valuation (`wealth/valuation/stock.py`, `crypto.py`, `gold.py`) — dùng giá user nhập tay, không update tự động

Hệ quả: User mở app, nhìn portfolio thấy giá đứng yên — niềm tin vào sản phẩm bị tổn hại. Đây là **blocker cho soft launch tháng 6**.

### Phase 3.9 giải quyết gì

Thay thế tất cả stub bằng **real-time integration** với các nguồn dữ liệu công khai của Việt Nam:

| Asset | Provider chính | Backup | Tần suất update |
|---|---|---|---|
| Stocks (HOSE/HNX) | SSI iBoard | VNDIRECT | 15 phút (giờ giao dịch) |
| Crypto | CoinGecko | — | 5 phút |
| Gold | SJC scraping | PNJ scraping | 3 lần/ngày |
| Bank rates | Top 20 bank scrapers | — | Hàng tuần |
| Market news | RSS (cafef, vnexpress kinh doanh) | — | Hàng giờ |

Sau Phase 3.9, **morning briefing sẽ hiển thị số liệu thật** — đây là moment of trust với user.

### Phase 3.9 KHÔNG làm gì

Để tránh scope creep, các điểm sau **rõ ràng OUT-OF-SCOPE**:

- **Real-time push notifications** khi giá biến động — chỉ scheduled alerts (Story S18)
- **Trading execution** — Phase 3.9 chỉ READ data, không có buy/sell
- **Historical backtesting** — chỉ snapshot hiện tại, không lưu history charts
- **Real estate price index** — vẫn là user-input (đã quyết định Phase 3A)
- **International stocks** — chỉ VN market
- **Forex/exchange rates** — defer sang phase sau (mặc dù đã được nhắc trong roadmap)
- **Premium data feeds** (Bloomberg, Refinitiv) — không cần thiết, free sources đủ

---

## 2. Architecture Overview

### High-level data flow

```
┌─────────────────────────────────────────────────────────────┐
│  EXTERNAL DATA SOURCES                                      │
│  ┌────────┐  ┌──────────┐  ┌─────┐  ┌─────────┐  ┌─────┐  │
│  │ SSI    │  │CoinGecko │  │ SJC │  │ Banks   │  │ RSS │  │
│  │VNDIRECT│  │          │  │ PNJ │  │ (x20)   │  │ feed│  │
│  └───┬────┘  └────┬─────┘  └──┬──┘  └────┬────┘  └──┬──┘  │
└──────┼────────────┼───────────┼──────────┼──────────┼─────┘
       │            │           │          │          │
       ▼            ▼           ▼          ▼          ▼
┌─────────────────────────────────────────────────────────────┐
│  PROVIDER LAYER (app/market_data/providers/)                │
│  Mỗi provider: fetch + parse + normalize → unified format   │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  CACHE LAYER (Redis)                                        │
│  TTL strategies: 5min stocks/crypto, 1h gold, 24h banks     │
└─────────────────────┬───────────────────────────────────────┘
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
┌────────────┐ ┌──────────────┐ ┌────────────────┐
│ Wealth     │ │ Morning      │ │ Agent Tools    │
│ Valuation  │ │ Briefing     │ │ (Phase 3.7)    │
│ (real $)   │ │ Renderer     │ │ replace stubs  │
└────────────┘ └──────────────┘ └────────────────┘
```

### Folder structure (mới + điều chỉnh)

```
app/
├── market_data/                      # ⭐ NEW
│   ├── __init__.py
│   ├── base.py                       # BaseProvider abstract class
│   ├── normalizer.py                 # Unified PriceQuote dataclass
│   ├── exceptions.py                 # MarketDataError, ProviderUnavailable, etc.
│   │
│   ├── providers/
│   │   ├── stock_ssi.py              # SSI iBoard primary
│   │   ├── stock_vndirect.py         # VNDIRECT backup
│   │   ├── stock_dispatcher.py       # SSI → VNDIRECT fallback logic
│   │   ├── crypto_coingecko.py
│   │   ├── gold_sjc.py
│   │   ├── gold_pnj.py
│   │   ├── gold_dispatcher.py        # SJC → PNJ fallback
│   │   ├── bank_rates_scraper.py     # Multi-bank, generic
│   │   └── news_rss.py
│   │
│   ├── cache/
│   │   ├── price_cache.py            # Redis wrapper, TTL config
│   │   └── cache_keys.py             # Key naming convention
│   │
│   ├── jobs/                         # APScheduler tasks
│   │   ├── stock_updater.py          # 15min during market hours
│   │   ├── crypto_updater.py         # 5min always
│   │   ├── gold_updater.py           # 3x/day
│   │   ├── bank_rates_updater.py     # Weekly
│   │   └── news_updater.py           # Hourly
│   │
│   └── analytics/
│       ├── portfolio_metrics.py      # YTD return, best/worst
│       └── alerts.py                 # Big movement detector
│
├── wealth/
│   └── valuation/
│       ├── stock.py                  # 🔧 EDIT: use market_data cache
│       ├── crypto.py                 # 🔧 EDIT
│       └── gold.py                   # 🔧 EDIT
│
├── briefing/
│   └── morning_briefing.py           # 🔧 EDIT: enrich with real data
│
└── agent/
    └── tools/
        └── market_query.py           # 🔧 EDIT: replace stubs
```

**Lý do tách `market_data/` thành module riêng:**
- Cô lập một concern (gọi external APIs) khỏi business logic
- Dễ mock trong unit test
- Dễ swap providers sau này (vd: thay SSI bằng provider mới)
- Clear cache invalidation boundary

---

## 3. Provider Layer — Thiết kế chi tiết

### 3.1 BaseProvider abstract class

Mọi provider implement chung interface để code dùng polymorphism (không cần if/else theo provider):

```python
# app/market_data/base.py
from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime
from decimal import Decimal

class PriceQuote:
    """Unified format cho mọi loại giá."""
    symbol: str               # "VNM", "BTC", "SJC_GOLD"
    price: Decimal            # Luôn là Decimal, không float
    currency: str             # "VND", "USD"
    asset_type: str           # "stock" | "crypto" | "gold" | "bank_rate"
    fetched_at: datetime      # Khi nào provider trả về
    source: str               # "ssi" | "vndirect" | "coingecko" | "sjc" | "pnj"
    metadata: dict            # Provider-specific extras (volume, change%, etc.)

class BaseProvider(ABC):
    @abstractmethod
    async def fetch_quote(self, symbol: str) -> PriceQuote: ...

    @abstractmethod
    async def fetch_batch(self, symbols: list[str]) -> list[PriceQuote]:
        """Batch nếu provider support, fallback gọi tuần tự nếu không."""

    @property
    @abstractmethod
    def asset_type(self) -> str: ...
```

**Tại sao cần `PriceQuote` object thay vì `dict`?**
- Type safety: IDE autocomplete, type checker bắt lỗi sớm
- Schema rõ ràng: tất cả downstream consumers đều biết structure
- Dễ migrate sau: thêm field mà không break code cũ

### 3.2 Stock Providers

**SSI iBoard (primary):**
- API: `https://iboard-api.ssi.com.vn/...` (public, không cần API key cho data cơ bản)
- Endpoint chính: `/v2/stock/quote` cho real-time, `/v2/stock/historical` cho lịch sử (Phase 3.9 chỉ dùng quote)
- Rate limit: ~60 req/min (chưa confirm chính xác — implement với rate limiter để safe)
- Response time: thường < 500ms

**VNDIRECT (backup):**
- API: `https://finfo-api.vndirect.com.vn/...`
- Cũng public, schema khác SSI
- Dùng khi SSI fail (timeout, error 5xx, hoặc 429 rate limit)

**Fallback logic** (`stock_dispatcher.py`):

```python
async def get_stock_quote(symbol: str) -> PriceQuote:
    try:
        # Try SSI first (3s timeout)
        return await asyncio.wait_for(
            ssi_provider.fetch_quote(symbol),
            timeout=3.0
        )
    except (TimeoutError, ProviderUnavailable, RateLimitError) as e:
        logger.warning(f"SSI failed for {symbol}: {e}, fallback to VNDIRECT")
        # Try VNDIRECT (5s timeout)
        return await asyncio.wait_for(
            vndirect_provider.fetch_quote(symbol),
            timeout=5.0
        )
    # If both fail → raise MarketDataError, caller handles
```

**Circuit breaker pattern** (đề xuất cho production hardening):
- Nếu SSI fail liên tiếp 5 lần trong 1 phút → "open circuit", skip SSI trong 5 phút, đi thẳng VNDIRECT
- Sau 5 phút → "half-open": cho 1 request thử, nếu OK → "closed" lại
- Library: `circuitbreaker` (Python) hoặc tự implement đơn giản với Redis counter

→ Phase 3.9 implement circuit breaker đơn giản, không cần lib bên ngoài.

### 3.3 Crypto Provider — CoinGecko

- API: `https://api.coingecko.com/api/v3/`
- Free tier: 10-30 req/min (varies)
- Public, không cần API key cho basic
- Endpoint: `/simple/price?ids=bitcoin,ethereum&vs_currencies=usd,vnd`

Lưu ý quan trọng:
- CoinGecko trả giá theo `coin_id` (vd: "bitcoin"), không phải ticker (vd: "BTC")
- Cần mapping table: `BTC → bitcoin`, `ETH → ethereum`, `SOL → solana`, ...
- Mapping lưu trong `app/market_data/providers/coingecko_symbols.py`

**Currency:** Lấy giá ở cả USD và VND. CoinGecko có sẵn VND. Nếu muốn double-check, có thể cross-validate USD * tỷ giá. Phase 3.9 trust thẳng VND của CoinGecko.

### 3.4 Gold Provider — SJC + PNJ scraping

**Tại sao scrape thay vì gọi API?** SJC và PNJ không có API public. Đây là tradeoff phải chấp nhận.

**SJC scraper:**
- URL: `https://sjc.com.vn/giavang/textContent.php` (HTML page có table giá)
- Parse với BeautifulSoup
- Cấu trúc: tên loại vàng (SJC, nhẫn 24K) + Giá mua + Giá bán + Thời gian update
- Update frequency của SJC: ~3 lần/ngày (sáng, trưa, chiều)

**PNJ scraper (backup):**
- URL: `https://www.pnj.com.vn/blog/gia-vang/`
- Parse tương tự
- Dùng khi SJC HTML thay đổi structure (bị break)

**Cảnh báo:** Scraping luôn fragile. Có 2 mitigations:
1. **Snapshot test:** Lưu HTML mẫu vào `tests/fixtures/sjc_sample.html`, parser test phải pass với fixture này
2. **Health check job:** Cron 1 lần/ngày kiểm tra parser còn work không, nếu fail → push alert vào Telegram của owner (không phải user)

### 3.5 Bank Rates Aggregator

20 ngân hàng có cấu trúc HTML rất khác nhau → không thể có một parser dùng chung.

**Strategy:**
- Mỗi bank có 1 file parser riêng: `bank_parsers/vcb.py`, `bank_parsers/techcombank.py`, ...
- Mỗi parser implement interface `parse_rates(html: str) -> list[BankRate]`
- `bank_rates_scraper.py` orchestrate: gọi từng parser, gom kết quả
- Nếu 1 bank fail → log error, skip bank đó, không break job

**Top 20 banks (ưu tiên theo market share):**
VCB, BIDV, Agribank, Vietinbank, Techcombank, MBBank, ACB, VPBank, Sacombank, HDBank, SHB, TPBank, OCB, MSB, VIB, SeABank, Eximbank, NamA Bank, BacABank, LPBank.

**BankRate schema:**
```python
class BankRate:
    bank_code: str       # "VCB", "TCB"
    bank_name: str       # "Vietcombank"
    tenor_months: int    # 1, 3, 6, 12, 24
    rate_pct: Decimal    # Lãi suất % năm
    deposit_type: str    # "regular" | "online" | "promo"
    fetched_at: datetime
    notes: Optional[str] # "Số tiền >= 500tr", "Khách VIP", v.v.
```

**Critical:** Bank rates change weekly hoặc theo policy → tần suất update **HÀNG TUẦN là đủ** (chạy sáng thứ 2). Update nhiều hơn không cần thiết và spam server của bank.

### 3.6 News Provider — RSS Feed

**Sources:**
- cafef.vn: `https://cafef.vn/thi-truong-chung-khoan.rss`
- vnexpress kinh doanh: `https://vnexpress.net/rss/kinh-doanh.rss`
- (Optional) Tin nhanh chứng khoán, ndh.vn

**Parser:** `feedparser` (Python lib chuẩn)

**Workflow:**
1. Cron 1h fetch RSS → parse entries
2. Lưu vào `news_articles` table (PostgreSQL): id, title, summary, url, published_at, source, **embedding** (optional)
3. Khi user mở morning briefing → query 3 articles mới nhất

**LLM summarization tied to holdings (Story S15):**

Khi render briefing, gọi DeepSeek với prompt:
```
User holdings: VNM (200 cổ), HPG (100 cổ), VIC (50 cổ)
News last 24h:
1. [VNM]: "Vinamilk báo cáo Q2..."
2. [Market]: "VN-Index tăng 1.5%..."
3. [HPG]: "Hòa Phát tăng giá thép..."

Task: Summarize top 3 most relevant news for THIS user, max 1 sentence each.
Filter rule: news mentioning user's tickers > general market news > others.
```

**Cost concern:** Mỗi briefing = 1 LLM call ~500 tokens. Với 1 briefing/ngày/user = ~$0.001/user/ngày. OK cho scale soft launch.

---

## 4. Cache Layer (Redis)

### 4.1 Tại sao cần cache?

3 lý do:
1. **Rate limiting:** Free APIs có rate limit. Nếu mỗi request từ user gọi API trực tiếp → vượt limit ngay với 10 users đồng thời.
2. **Latency:** API call ~500ms-2s. Cache hit ~5ms. UX khác biệt rõ rệt.
3. **Cost:** Một số API tính phí khi vượt free tier. Cache giảm số call.

### 4.2 TTL Strategy (Time-To-Live)

| Asset | TTL | Lý do |
|---|---|---|
| Stocks | 5 phút | Giá thay đổi nhanh trong giờ giao dịch, ngoài giờ vẫn show stale OK |
| Crypto | 2 phút | 24/7 trading, biến động nhanh |
| Gold | 1 giờ | SJC chỉ update 3 lần/ngày, không cần refresh nhiều |
| Bank rates | 7 ngày | Rates ổn định cả tuần |
| News | 30 phút | Cân bằng giữa freshness và load |

### 4.3 Cache key naming

```
market_data:stock:VNM           → PriceQuote(VNM)
market_data:crypto:BTC          → PriceQuote(BTC)
market_data:gold:SJC_24K        → PriceQuote
market_data:bank_rate:VCB:12m   → BankRate
market_data:news:latest:5       → list of 5 latest News objects
market_data:health:ssi          → "ok" | "down" (circuit breaker state)
```

**Key prefix `market_data:` quan trọng để:**
- Dễ flush riêng phần này (`redis-cli --scan --pattern "market_data:*" | xargs redis-cli DEL`)
- Tách namespace với các cache khác (session, intent, etc.)

### 4.4 Cache-aside pattern

```python
async def get_stock_quote(symbol: str) -> PriceQuote:
    cache_key = f"market_data:stock:{symbol}"

    # 1. Try cache
    cached = await redis.get(cache_key)
    if cached:
        return PriceQuote.from_json(cached)

    # 2. Cache miss → call provider
    quote = await stock_dispatcher.get_quote(symbol)

    # 3. Write to cache (TTL 5min)
    await redis.setex(cache_key, 300, quote.to_json())

    return quote
```

**Edge case — stale-while-revalidate:**
Nếu provider down, có nên trả cache đã hết hạn? Phase 3.9 dùng strategy đơn giản:
- Cache hit (in TTL) → return ngay
- Cache miss + provider OK → fetch, cache, return
- Cache miss + provider down → return last known price từ Redis backup key (`market_data:stock:VNM:last_known`, no TTL), kèm flag `is_stale=True`
- Briefing render → nếu `is_stale=True`, hiển thị cảnh báo "(giá cũ từ 2h trước)"

### 4.5 Pre-warming cache

Background jobs (Section 5) chạy theo lịch để **pre-warm cache** cho tất cả stocks/crypto/gold mà user trong hệ thống đang hold. Khi user mở briefing, đa số case là cache hit → nhanh.

---

## 5. Update Jobs (APScheduler)

### 5.1 Lịch update

```python
# app/market_data/jobs/__init__.py — register vào APScheduler

SCHEDULES = {
    "stock_price_updater": {
        "trigger": "cron",
        "minute": "*/15",         # Mỗi 15 phút
        "hour": "9-15",           # 9:00-15:00 (giờ giao dịch HOSE)
        "day_of_week": "mon-fri", # T2-T6
    },
    "crypto_price_updater": {
        "trigger": "interval",
        "minutes": 5,             # Mỗi 5 phút, 24/7
    },
    "gold_price_updater": {
        "trigger": "cron",
        "hour": "9,13,16",        # 3 lần/ngày: sáng, trưa, chiều
        "minute": 0,
    },
    "bank_rates_updater": {
        "trigger": "cron",
        "day_of_week": "mon",     # Sáng thứ 2
        "hour": 6,
        "minute": 0,
    },
    "news_updater": {
        "trigger": "interval",
        "hours": 1,               # Mỗi giờ
    },
    "provider_health_check": {
        "trigger": "cron",
        "hour": 7,                # Sáng 7h, trước briefing
        "minute": 30,
    },
}
```

### 5.2 Job logic generic

Mỗi job theo cùng pattern:

```python
async def stock_price_updater():
    # 1. Get all stocks held by any user (distinct)
    held_symbols = await db.fetch_distinct_held_stocks()
    if not held_symbols:
        return  # No-op nếu không có user nào hold stock

    # 2. Batch fetch (use provider batch API if available)
    quotes = await stock_dispatcher.fetch_batch(held_symbols)

    # 3. Write to cache
    for q in quotes:
        await price_cache.set(q)
        await price_cache.set_last_known(q)  # Backup for stale-while-revalidate

    # 4. Log metrics
    logger.info(f"stock_updater: fetched {len(quotes)}/{len(held_symbols)} symbols")

    # 5. Check for big movements → trigger alerts (Story S18)
    await alert_service.check_movements(quotes)
```

### 5.3 Why "fetch only held symbols" thay vì toàn HOSE?

- HOSE có ~700 stocks. Fetch hết = waste bandwidth + rate limit.
- User trong hệ thống thực tế chỉ hold ~5-50 stocks tổng cộng.
- Trade-off: Khi user thêm stock mới chưa từng có → cache miss, gọi API lần đầu (chấp nhận được, cold start ~1s).

### 5.4 Failure handling

- Job throw exception → APScheduler log nhưng không crash service
- Mỗi job có metrics: `last_run_at`, `last_run_status`, `last_run_duration_ms` → lưu vào Redis
- Owner có thể kiểm tra `/admin/jobs/health` (admin endpoint, internal only)

---

## 6. Wealth Valuation Integration (Story S9)

### 6.1 Trước Phase 3.9

```python
# app/wealth/valuation/stock.py (CURRENT)
def value_stock_holding(holding: StockHolding) -> Decimal:
    # Dùng giá user nhập tay khi tạo asset
    return holding.shares * holding.user_input_price
```

### 6.2 Sau Phase 3.9

```python
# app/wealth/valuation/stock.py (NEW)
async def value_stock_holding(holding: StockHolding) -> Decimal:
    quote = await market_data.get_stock_quote(holding.symbol)
    return holding.shares * quote.price
```

### 6.3 Migration concern

User trước đây tạo holding với giá tự nhập (vd: VNM mua giá 70k). Sau khi switch sang real-time, giá hiển thị có thể khác → user surprise.

**Solution:**
- Giữ field `user_input_price` trong DB → đây là **cost basis** (giá mua), KHÔNG bỏ
- Thêm field display ngữ cảnh: "Cost basis: 70k → Current price: 72.5k → P/L: +3.5%"
- Đây thực ra là **upgrade UX** chứ không phải breaking change. Người dùng sẽ vui.

---

## 7. Enhanced Morning Briefing (Story S16)

### 7.1 Trước Phase 3.9 (briefing hiện tại)

```
☀️ Chào anh Phương!
Tổng tài sản: 2,450,000,000 đ
Thay đổi tuần: +12,500,000 đ
Top assets:
- BĐS Quận 7: 1,500,000,000
- Stocks: 450,000,000
- Cash: 500,000,000
```

→ Static, không có market context.

### 7.2 Sau Phase 3.9

```
☀️ Chào anh Phương! Hôm nay là Thứ 4, 12/06/2026

📊 TỔNG TÀI SẢN: 2,475,000,000 đ
   ↑ +25tr (1.0%) so với hôm qua
   ↑ +75tr (3.1%) so với tuần trước

📈 THỊ TRƯỜNG SÁNG NAY
   • VN-Index: 1,285.4 (▲ +0.8%)
   • Vàng SJC: 78,500,000 ₫/lượng (▲ +0.3%)
   • BTC: 1,650,000,000 ₫ (▼ -1.2%)

💼 PORTFOLIO CỦA ANH
   • Stocks (30%): 742tr ▲ +1.2% (best: HPG +3.5%, worst: VIC -0.8%)
   • Crypto (5%): 124tr ▼ -0.9%
   • Vàng (8%): 198tr ▲ +0.3%
   • BĐS (45%): 1,114tr (giá user-input)
   • Cash (12%): 297tr (lãi 0.5%/tháng tại VCB)

📰 TIN ĐÁNG CHÚ Ý (liên quan đến anh)
   1. [HPG] Hòa Phát công bố KQKD Q2 vượt kỳ vọng
   2. [VN-Index] Khối ngoại mua ròng phiên thứ 3 liên tiếp
   3. [Lãi suất] VCB tăng lãi tiết kiệm 12m lên 5.2%

💡 LƯU Ý
   • HPG đang tăng mạnh, có thể chốt lời 1 phần?
   • Lãi suất VCB tăng — anh đang gửi MB rate 4.8%, cân nhắc chuyển?
```

### 7.3 Implementation breakdown

Briefing renderer cần kết hợp data từ nhiều nguồn:

```python
async def render_morning_briefing(user_id: UUID) -> str:
    # Gọi parallel để tối ưu latency
    portfolio = await wealth.get_portfolio(user_id)
    market = await market_data.get_market_overview()  # VN-Index, gold ref price, BTC ref
    portfolio_metrics = await analytics.compute_portfolio_metrics(user_id)
    news = await news_service.get_relevant_news(user_id, limit=3)
    insights = await insight_service.generate_insights(user_id, portfolio, market)

    return briefing_template.render(
        user=user, portfolio=portfolio, market=market,
        metrics=portfolio_metrics, news=news, insights=insights
    )
```

**Latency target:** < 2 giây total (thanks to cache).

**Localization:** Toàn bộ template strings nằm trong `content/briefing.yaml` để dễ tweak persona "Bé Tiền" mà không phải edit code.

---

## 8. Portfolio Analytics (Story S17)

3 metrics chính, tính từ data đã có (không cần thêm DB):

### 8.1 YTD Return

```python
def compute_ytd_return(holding: StockHolding, current_price: Decimal) -> dict:
    # Lấy giá đầu năm (1/1/YYYY) từ historical snapshot
    start_year_price = get_price_on(holding.symbol, date(YEAR, 1, 1))
    if not start_year_price:
        return {"available": False}

    return_pct = (current_price - start_year_price) / start_year_price * 100
    return {
        "available": True,
        "return_pct": return_pct,
        "absolute": (current_price - start_year_price) * holding.shares,
    }
```

**Nguồn historical:** SSI có endpoint `/historical?from=2026-01-01&to=2026-01-02`. Phase 3.9 fetch một lần đầu năm cho mỗi stock user hold, lưu DB (`stock_historical_prices` table).

### 8.2 Best/Worst Performer

Sort holdings theo % change today (từ cached quote `metadata.change_pct`):

```python
def get_best_worst(holdings: list[StockHolding]) -> tuple[StockHolding, StockHolding]:
    sorted_h = sorted(holdings, key=lambda h: h.today_change_pct, reverse=True)
    return sorted_h[0], sorted_h[-1]
```

### 8.3 Diversification Score

Heuristic đơn giản (Phase 3.9 chỉ làm v1, không quá khoa học):

```python
def diversification_score(portfolio: Portfolio) -> int:
    # 0-100, càng cao càng diversified
    asset_types = portfolio.asset_type_distribution()  # {"stock": 0.3, "bond": 0.0, ...}
    n_types_with_meaningful_pct = sum(1 for pct in asset_types.values() if pct > 0.05)

    # 5+ types với each > 5% → high score
    # 1-2 types → low score
    type_score = min(n_types_with_meaningful_pct * 20, 80)

    # Penalty nếu 1 stock chiếm > 30% portfolio
    max_single_holding_pct = max(h.pct_of_total for h in portfolio.stocks)
    concentration_penalty = max(0, (max_single_holding_pct - 30) * 0.5)

    return max(0, min(100, type_score - concentration_penalty + 20))
```

→ Output: `"Diversification: 65/100 (Trung bình)"`. Phase 4 hoặc sau có thể dùng correlation matrix cho chính xác hơn.

---

## 9. Price Alerts (Story S18)

### 9.1 Logic

Sau mỗi `stock_price_updater` chạy, so sánh quote mới với quote cũ:

```python
async def check_movements(new_quotes: list[PriceQuote]):
    for q in new_quotes:
        prev = await price_cache.get_last_known(q.symbol, before=q.fetched_at - timedelta(minutes=15))
        if not prev:
            continue

        change_pct = (q.price - prev.price) / prev.price * 100

        if abs(change_pct) >= 5.0:  # >= 5% threshold
            users_holding = await db.find_users_holding(q.symbol)
            for user in users_holding:
                await alert_service.send(
                    user_id=user.id,
                    severity="info" if abs(change_pct) < 7 else "warning",
                    message=f"{q.symbol} {'tăng' if change_pct > 0 else 'giảm'} "
                            f"{abs(change_pct):.1f}% trong 15 phút qua "
                            f"(từ {prev.price:,.0f} → {q.price:,.0f})"
                )
```

### 9.2 Anti-spam rules

- Maximum 3 alerts/user/ngày (priority queue, drop low-severity nếu vượt)
- Cool-down 30 phút giữa 2 alerts cho cùng 1 symbol
- User có thể disable alerts qua `/settings`

### 9.3 Delivery

Phase 3.9 chỉ làm Telegram message (không cần push notification riêng). Reuse `telegram_sender.py` đã có từ Phase 3.

---

## 10. Error Handling Strategy

### 10.1 Error taxonomy

```python
# app/market_data/exceptions.py
class MarketDataError(Exception): ...                  # Base
class ProviderUnavailable(MarketDataError): ...        # API down, timeout
class RateLimitError(MarketDataError): ...             # 429
class ParserError(MarketDataError): ...                # HTML structure changed
class SymbolNotFound(MarketDataError): ...             # Invalid ticker
class StaleDataWarning(MarketDataError): ...           # Returning cached data > TTL
```

### 10.2 Caller behavior matrix

| Error | Briefing renderer | Wealth valuation | Agent tool |
|---|---|---|---|
| `ProviderUnavailable` | Show last known + warning banner | Use `user_input_price` fallback | Tell user "không lấy được data, thử lại sau" |
| `SymbolNotFound` | Skip symbol, log | Treat as 0 (with warning) | Tell user "ticker không hợp lệ" |
| `ParserError` | Same as Provider down | Same | Same + alert owner |
| `StaleDataWarning` | Show stale banner | Use stale value | Tell user "(giá cũ Xh trước)" |

### 10.3 Owner monitoring

- Slack/Telegram channel riêng cho owner: `#bot-alerts`
- Mỗi `ParserError` → message tới channel: "SJC parser failed at 14:32, fallback to PNJ working"
- Daily summary 9h sáng: "Provider health: SSI 99.2%, VNDIRECT 100%, SJC 87% (3 fails)"

---

## 11. Testing Strategy

### 11.1 Unit tests
- Mỗi provider: mock HTTP response, assert parsed `PriceQuote` đúng
- Cache: assert TTL behavior, assert stale-while-revalidate
- Dispatcher: assert fallback đúng thứ tự, assert circuit breaker

### 11.2 Integration tests
- End-to-end flow: provider → cache → wealth valuation → briefing render
- Use real Redis (testcontainers), mock HTTP

### 11.3 Snapshot tests cho scrapers
- Lưu HTML mẫu của SJC, PNJ, mỗi bank vào `tests/fixtures/`
- Mỗi tuần chạy 1 job kiểm tra fixture vs live (cảnh báo nếu khác → có thể parser sắp break)

### 11.4 Manual test plan
Xem [phase-3.9-test-cases.md](./phase-3.9-test-cases.md) — ~85 test cases.

### 11.5 Performance benchmarks
- Briefing render: P95 < 2s (cache hit)
- Cache miss + provider call: P95 < 3s
- Bank rates job (20 banks): < 60s total

---

## 12. Rollout Plan

### 12.1 Phased rollout

**Phase A — Tuần 1 (Stock + Crypto):**
- Ship: SSI/VNDIRECT integration, CoinGecko, cache layer, stock + crypto updaters
- Validate: Owner check briefing có giá đúng không, so với app SSI iBoard

**Phase B — Tuần 2 (Gold + Bank + News):**
- Ship: SJC + PNJ scrapers, bank rates aggregator, news RSS
- Validate: Snapshot tests pass, owner verify giá vàng so với sjc.com.vn

**Phase C — Tuần 3 (Briefing + Analytics + Alerts):**
- Ship: Enhanced briefing template, portfolio metrics, price alerts
- Validate: 5 ngày live briefing, owner self-test on weekend

### 12.2 Feature flags

Mỗi component có flag tắt/bật trong `app/config.py`:
```python
MARKET_DATA_ENABLED = True
MARKET_DATA_USE_REAL_STOCKS = True   # Off → fallback to user_input_price
MARKET_DATA_USE_REAL_GOLD = False    # Off đến khi snapshot test pass
MARKET_DATA_NEWS_ENABLED = True
MARKET_DATA_ALERTS_ENABLED = False   # On sau cuối tuần 3
```

→ Rollback dễ dàng nếu phát hiện bug nghiêm trọng.

---

## 13. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SSI/VNDIRECT thay đổi API breaking | Medium | High | Snapshot tests, monitoring, có VNDIRECT backup |
| SJC/PNJ HTML structure change | High | Medium | Snapshot tests, fallback PNJ, owner alert |
| Free API rate limit hit | Medium | Medium | Cache aggressive, batch requests, exponential backoff |
| Briefing latency > 5s do API chậm | Medium | High | Pre-warm cache via jobs, parallel fetch, timeout 3s |
| Provider trả giá sai → wealth tính sai | Low | High | Cross-validate (SSI vs VNDIRECT), sanity check (price drop > 30% → suspicious) |
| Bank rate parser break cho 5+ banks | Medium | Low | Skip bad banks, log, không break briefing |
| News irrelevance (LLM pick sai) | Medium | Low | Manual review trong 1 tuần đầu, tweak prompt |

---

## 14. Open Questions

1. **SSI iBoard có cần auth?** — Cần test với production credentials trước khi release. Nếu cần API key, cần xin SSI và setup secrets.
2. **News articles caching policy?** — Có nên dedupe articles giống nhau từ nhiều sources? Phase 3.9 v1: chỉ dedupe theo URL.
3. **Bank rates: hiển thị net rate (sau thuế) hay gross rate?** — Quy ước: hiển thị gross (số ngân hàng quảng cáo). Sau Phase 3.9 có thể thêm option.
4. **Diversification score: có nên expose số? Hay chỉ dùng từ "Tốt/Trung bình/Yếu"?** — Phase 3.9 expose số cho người thích metrics, nhưng kèm label categorical. A/B test trong Phase 4.

---

## 15. Dependencies & Setup

### 15.1 Python packages mới

```
# requirements.txt additions
httpx>=0.27          # Async HTTP client (thay requests)
beautifulsoup4>=4.12 # Đã có từ phase trước
feedparser>=6.0      # RSS parsing
redis>=5.0           # Đã có
apscheduler>=3.10    # Đã có
```

### 15.2 Environment variables mới

```
# .env additions
SSI_API_BASE_URL=https://iboard-api.ssi.com.vn
VNDIRECT_API_BASE_URL=https://finfo-api.vndirect.com.vn
COINGECKO_API_BASE_URL=https://api.coingecko.com/api/v3

# Optional, for higher rate limits later
SSI_API_KEY=
COINGECKO_PRO_KEY=

# Owner alerts
OWNER_ALERT_TELEGRAM_CHAT_ID=  # Chat riêng nhận alert SJC parser fail, etc.
```

### 15.3 Database migrations

```sql
-- New table
CREATE TABLE stock_historical_prices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL,
    price NUMERIC(20,2) NOT NULL,
    snapshot_date DATE NOT NULL,
    source VARCHAR(20) NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(symbol, snapshot_date)
);
CREATE INDEX idx_historical_symbol_date ON stock_historical_prices(symbol, snapshot_date);

-- New table
CREATE TABLE news_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    summary TEXT,
    url TEXT NOT NULL UNIQUE,
    source VARCHAR(50) NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    related_symbols VARCHAR[] DEFAULT '{}',
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_news_published ON news_articles(published_at DESC);
CREATE INDEX idx_news_symbols ON news_articles USING GIN(related_symbols);

-- New table
CREATE TABLE bank_rates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bank_code VARCHAR(20) NOT NULL,
    bank_name VARCHAR(100) NOT NULL,
    tenor_months INTEGER NOT NULL,
    rate_pct NUMERIC(5,3) NOT NULL,
    deposit_type VARCHAR(20) NOT NULL,
    notes TEXT,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(bank_code, tenor_months, deposit_type, snapshot_date)
);
CREATE INDEX idx_bank_rates_lookup ON bank_rates(bank_code, snapshot_date DESC);

-- New table
CREATE TABLE price_alerts_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    symbol VARCHAR(20) NOT NULL,
    change_pct NUMERIC(6,2) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_alerts_user_sent ON price_alerts_log(user_id, sent_at DESC);
```

---

## 16. Reference Links

- Phase 3.7 detailed: [docs/current/phase-3.7-detailed.md](./phase-3.7-detailed.md) — agent architecture, market_query tool stub
- Phase 3.8 detailed: [docs/current/phase-3.8-detailed.md](./phase-3.8-detailed.md) — wealth completion
- Phase 3.8.5 detailed: [docs/current/phase-3.8.5-detailed.md](./phase-3.8.5-detailed.md) — feedback + profile
- Phase 4A planning: [docs/planned/phase-4-twin.md](../planned/phase-4-twin.md) — depends on real market data

---

**Phase 3.9 = real money numbers. Sau phase này, mọi thứ user nhìn thấy đều thật. 💚📊**
