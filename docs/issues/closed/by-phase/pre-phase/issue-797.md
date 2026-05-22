# Issue #797

[perf] Tier 1 intent classifier latency 10s+ — Groq llama-3.3-70b not actually used


## Nguyên nhân

Khi user gõ free-form text, bot gọi /api/v1/telegram/webhook → gọi LLM để classify intent. 
Log  từ  ghi nhận latency_ms dao động:

| Thời gian | Intent | latency_ms |
|---|---|---|
| 15:00:52 | query_assets | **9,894ms** |
| 15:26:42 | query_goals | **843ms** (hiếm) |
| 15:32:35 | query_assets | **10,335ms** |
| 17:31:47 | report_text (DeepSeek) | **26,087ms ❌ FAIL** |

Code config có Groq (llama-3.3-70b-versatile) dùng cho Tier 1 classifier với sub-second latency, nhưng thực tế:
- Groq API còn hoạt động: test latency **425-759ms** (đã verify 17:38)
-  chỉ ghi *deepseek* calls, không có *groq* — Groq không được gọi
- Classifier đang dùng DeepSeek V4-Flash (first-token latency 4-12s batch-oriented) thay vì Groq

## Evidence

**Log intent_classified:**
- `"classifier": "agent_tier1", "latency_ms": 9894`
- `"classifier": "agent_tier1", "latency_ms": 10335`

**Log llm_cost_log (chỉ có deepseek):**
- `01:12 parse_receipt 1.1s deepseek-v4-flash`
- `15:33 report_text 13.9s deepseek-v4-flash`
- `16:01 report_text 12.8s deepseek-v4-flash`
- `17:31 report_text 26.1s deepseek-v4-flash FAIL`

**Groq API test (17:38):**
- Chat đơn giản: 425ms
- Intent classify: 759ms
- Chạy song song: 608ms vs Deepseek 1,129ms

## Files liên quan

- `backend/services/llm_service.py` — dòng 25-27 comment ghi "Groq powers Tier 1 NLU classifier — sub-second first-token latency"
- `backend/intent/classifier/llm_based.py` — classifier routing
- `backend/agent/orchestrator.py` — agent-routing từ commit mới nhất
