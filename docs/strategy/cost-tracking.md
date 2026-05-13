## Cost Tracking

| Phase | Users | Infra/tháng | LLM/tháng | Total/tháng |
|---|---|---|---|---|
| Phase 0 | 1 | $0 (Mac Mini) | ~$5 | ~$5 |
| Phase 1 | 1,000 | ~$75 | ~$200 | ~$275 |
| Phase 2 | 10,000 | ~$700 | ~$1,500 | ~$2,200 |
| Phase 3 | 100,000 | ~$4,000 | ~$10,000 | ~$14,000 |
| Phase 4 | 1,000,000 | ~$25,000 | ~$80,000 | ~$105,000 |

**V2 cost optimizations:**
- Storytelling LLM calls cache aggressive (same-user same-day cache)
- DeepSeek cho text, Claude chỉ cho Vision
- Whisper cost: ~$0.006/phút → cache transcripts theo hash
- Market data: vnstock/CoinGecko/cafef free → no LLM cost
- Briefing generation: pure template + data → no LLM needed (chỉ Phase 3B market summary dùng LLM)

**Pricing tier V2 (justify LLM cost):**
- Free: Basic tracking, 1 asset type
- Pro (149k/tháng): All assets, morning briefing, DNA
- CFO (399k/tháng): Rental, advanced analytics, investment twin
