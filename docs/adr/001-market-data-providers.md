# ADR 001 — Phase 3.9 Market Data Providers

## Status
Accepted — Phase 3.9 ship gate.

## Context
Phase 3.9 replaces placeholder market prices with real public market data for Vietnamese users before soft launch. The product needs reliable read-only prices for morning briefing, wealth valuation, agent tools, and scheduled alerts without adding paid vendor cost too early.

## Decision

### Vietnamese stocks: SSI primary, VNDIRECT backup
- Use SSI iBoard as the primary provider because it has broad HOSE/HNX coverage, near-real-time quotes, and enough metadata for portfolio context: volume, change percent, high, low, and open.
- Use VNDIRECT as the backup provider because its response schema is different but normalizable to the same `PriceQuote` shape, making it a practical failover source.
- Route requests through the generic dispatcher and Redis-backed circuit breaker so a failing primary is skipped temporarily instead of being hammered.

### Crypto: CoinGecko free tier
- Use CoinGecko free tier because Phase 3.9 only needs common crypto spot prices in VND/USD and batch simple-price lookups.
- The current scheduled updater batches symbols and runs every 5 minutes, which keeps request volume acceptable for soft-launch scale.
- Add exponential backoff on rate-limit responses rather than adding a paid plan now.

### Gold: SJC primary, PNJ backup scraping
- Use SJC as primary because SJC is the locally recognizable benchmark for Vietnamese gold quotes.
- Use PNJ as backup because it provides a second public source with comparable buy/sell gold quote data.
- Scraping is accepted because no stable public SJC/PNJ JSON API is available for this scope. The parser layer is isolated so source layout changes are localized.

### Bank rates and news: public pages/RSS
- Scrape published savings rates from the top Vietnamese banks because rates change weekly and public bank pages are sufficient for comparison insights.
- Use RSS feeds for market news because they are lightweight, cache-friendly, and enough for holding-linked summaries.

## Upgrade triggers
Move to paid or contracted data feeds when any of these happens:

1. Cache hit rate remains below 80% after scheduled pre-warming.
2. Provider failures exceed the circuit-breaker threshold repeatedly during trading hours.
3. Live briefing P95 exceeds 2 seconds after provider/network latency optimization.
4. Soft-launch users require legal/compliance guarantees, historical backtesting, or higher-frequency intraday charts.
5. Public scraping layout churn creates more than two production parser fixes in one month.

## Consequences
- The system remains low-cost and good enough for trust-building during soft launch.
- Provider-specific parsing stays behind a normalized `PriceQuote` contract.
- Scrapers require monitoring because public HTML can change without notice.
- The decision intentionally avoids trading execution, premium market feeds, and international stocks until later phases.
