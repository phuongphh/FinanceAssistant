# Phase 3B — Market Intelligence (Outline)

> **Đây là outline cho Phase 3B, sẽ được detail hóa sau khi Phase 3A validation pass.**

> **Thời gian ước tính:** 3 tuần  
> **Prerequisites:** Phase 3A đã ship, có ít nhất 20 users active, retention D7 >40%

---

## 🎯 Mục Tiêu

Tự động cập nhật giá trị assets dựa trên market data real-time, biến morning briefing từ "đọc giá tài sản" thành **"intelligent financial advisor"**.

---

## 📅 Phân Bổ 3 Tuần

| Tuần | Nội dung |
|------|----------|
| **Tuần 1** | Stock + Crypto price integrations |
| **Tuần 2** | Gold + Bank rates + News |
| **Tuần 3** | Enhanced briefing + Portfolio analytics basic |

---

## 🔌 Data Sources Strategy

### 1. Vietnamese Stocks

**Primary:** SSI iBoard WebSocket
- Free for retail
- Real-time data
- Cần đăng ký API key

**Backup:** VNDIRECT REST API
- REST API
- Delay 15-20 phút (enough for our use case)
- Public, không cần key

**Emergency fallback:** Scraping cafef.vn
- Web scraping
- Rate limit care
- Use as last resort

**Data cần:**
- Giá khớp lệnh real-time (hoặc end-of-day)
- Volume
- Changes %
- VN-Index, VN30-Index

### 2. Crypto

**Primary:** CoinGecko API
- Free tier: 50 calls/phút
- Cover 99% coins
- Không cần API key cho basic

**Backup:** Binance public API
- Real-time
- Unlimited for price data
- Dùng cho top coins (BTC, ETH, BNB, USDT)

**Data cần:**
- Giá USD
- Giá VND (từ exchange rate)
- 24h change
- Top holdings của user

### 3. Gold

**Primary:** SJC website (scraping)
- sjc.com.vn/tra-cuu-gia-vang
- Update 2-3 lần/ngày
- Scheduled scrape 9h, 14h, 17h

**Secondary:** PNJ (scraping)
- pnj.com.vn

**Data cần:**
- Giá mua vào
- Giá bán ra
- Loại vàng (SJC, nhẫn 9999, trang sức)

### 4. Bank Interest Rates

**Source:** Top 20 banks scraping
- VCB, Techcom, MB, ACB, VPBank, BIDV, Agribank, etc.
- Scrape weekly
- Track rates for different tenors (3m, 6m, 12m, 24m)

**Data cần:**
- Lãi suất tiết kiệm từng kỳ hạn
- Điều kiện đặc biệt
- Track changes để alert user

### 5. Exchange Rates

**USD/VND:** Vietcombank rate (reference)

### 6. Market News (Optional tuần 3)

**Source:** RSS feed từ cafef.vn, vnexpress kinh doanh
- LLM summarize top 3 news
- Personalize based on user's holdings

---

## 🏗️ Architecture

```
app/
├── market_data/                  # ⭐ NEW
│   ├── providers/
│   │   ├── stock_provider.py     # SSI primary, VNDIRECT backup
│   │   ├── crypto_provider.py    # CoinGecko
│   │   ├── gold_provider.py      # SJC scraping
│   │   ├── bank_rates_provider.py
│   │   └── news_provider.py
│   ├── cache/
│   │   └── price_cache.py        # Redis-based, TTL 5min
│   ├── updater/
│   │   ├── stock_updater.py      # Cron job
│   │   ├── crypto_updater.py
│   │   └── gold_updater.py
│   └── normalizer.py             # Unified format
│
├── wealth/
│   └── valuation/
│       ├── stock.py              # Update: use real prices
│       ├── crypto.py             # Update
│       └── gold.py               # Update
│
└── scheduled/
    ├── stock_price_updater.py    # Every 15min during market hours
    ├── crypto_price_updater.py   # Every 5min
    ├── gold_price_updater.py     # 3x/day
    └── bank_rates_updater.py     # Weekly
```

---

## 📝 High-Level Tasks

### Tuần 1: Stock + Crypto

- [ ] Setup SSI iBoard API integration
- [ ] VNDIRECT backup fallback
- [ ] CoinGecko integration
- [ ] Price cache layer (Redis)
- [ ] Auto-update job cho stocks (every 15min)
- [ ] Auto-update job cho crypto (every 5min)
- [ ] Update `stock.py` và `crypto.py` valuation
- [ ] Snapshot jobs giờ dùng real prices
- [ ] Test với real portfolio

### Tuần 2: Gold + Bank Rates + News

- [ ] SJC scraping + parsing
- [ ] PNJ scraping
- [ ] Gold price update job
- [ ] Bank rate scraper cho top 20 banks
- [ ] Bank rate comparison feature
- [ ] News RSS feed integration
- [ ] LLM news summarization
- [ ] Tie news to user holdings

### Tuần 3: Enhanced Briefing + Polish

- [ ] Morning briefing enriched với:
  - VN-Index movements
  - User portfolio performance
  - News highlights
  - Bank rate changes (nếu có)
- [ ] Portfolio basic analytics:
  - YTD return
  - Best/worst performer
  - Diversification score
- [ ] Alert system: big price movements
- [ ] Testing + polish

---

## 🎨 Enhanced Morning Briefing Example (Mass Affluent)

```
☀️ Chào anh Phương! 7h30 sáng 24/04/2026

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💎 Giá trị ròng: 4.87 tỷ
📈 +32tr so với hôm qua (+0.66%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Phân bổ:
🏠 BĐS           2.5 tỷ   51%
📈 Chứng khoán   800tr   16%  🔥
💵 Tiền mặt      600tr   12%
₿  Crypto         250tr    5%
🥇 Vàng           220tr    5%
📦 Khác           500tr   11%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📰 Thị trường hôm nay:

• VN-Index đóng cửa hôm qua: 1,248.5 (+0.8%)
• Danh mục của anh: +1.2% ↑ (outperform)
• Top holding: VNM +2.1%, HPG +1.5%

• BTC: $67,200 (-1.2%)
• SJC Gold: 81.5tr/lượng (không đổi)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 Insight:

• 🏦 Techcom vừa tăng lãi suất TK 12m lên 6.2%.
  Bank hiện tại của anh (VCB): 5.8%
  → Tiết kiệm 400tr có thể tăng 1.6tr/năm nếu chuyển.
  [Xem chi tiết]

• 📈 HPG sắp chia cổ tức 15/5. Anh có 5,000 cp.
  Dự kiến nhận: ~7.5tr

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💭 Hôm qua có chi gì >500k không?

[💬 Kể] [✅ Không có]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[📊 Dashboard] [📈 Portfolio] [⚙️ Cài đặt]
```

---

## ⚠️ Risks

1. **API quota hit** — Cache aggressive, batch updates
2. **Scraping blocked** — Multiple sources, respect robots.txt
3. **Data discrepancies** — Cross-check sources, alert if >5% difference
4. **Market hours logic** — HOSE 9:00-11:30, 13:00-14:45 VN time
5. **Cost explosion** — LLM news summarization = $$ — limit to Mass Affluent+ tier

---

## 🎯 Success Metrics

- **Price update latency** <15min for stocks, <5min crypto
- **Data accuracy** >99% (cross-check with real bank app)
- **User perceived value** — briefing open rate +20% vs Phase 3A
- **Upgrade rate to Pro** — +15% conversions (market intel = key upsell)

---

**Detail version của file này sẽ được viết sau khi Phase 3A validation confirm user value prop. Chúng ta sẽ iterate dựa trên feedback thực tế trước khi invest 3 tuần vào integrations. 🚀**
