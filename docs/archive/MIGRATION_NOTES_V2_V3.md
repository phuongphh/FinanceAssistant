# MIGRATION NOTES: Strategy V2 → V3

> **Loại document:** ADR (Architecture Decision Record) for product strategy pivot
> **Ngày tạo:** May 2026
> **Status:** ✅ Adopted
> **Triggered by:** Post-Phase 3.7 strategic review session

---

## 📌 Context

Sau khi Phase 3.7 (Agent Architecture) ship thành công với 3-tier orchestrator + 5 tools + streaming, sản phẩm có **technical foundation mạnh**. Câu hỏi lớn xuất hiện: *Sản phẩm này differentiate thế nào với competitors (Money Lover, MISA, Spendee, Finhay, Tikop)?*

Strategy V2 đã pivot từ "expense tracking" sang "Personal CFO" với morning briefing là core hook. Tuy nhiên V2 vẫn chưa định hình rõ **what makes this product UNREPLACEABLE**.

Strategic review session diễn ra vào May 2026 với 2 con đường:

- **Path X (Incremental):** Polish existing features, ship gradually, compete on quality
- **Path Y (Differentiation):** Add a wow-factor feature that no Vietnamese app has, position as new category

---

## 🎯 Decision

**Adopted Path Y: Differentiation strategy with Financial Twin as primary wow-factor.**

Đồng thời, **adjust pricing xuống** để unlock volume play thay vì premium niche:
- Pro: 149k → **68k/tháng**
- CFO: 399k → **168k/tháng**

---

## 🤔 Reasoning

### Tại sao Twin (not other features)?

5 reasons agreed in review:

1. **Vietnam-specific gap** — Không có sản phẩm VN nào làm financial future visualization
2. **Mass Affluent psyche match** — Target users (30-50, 200tr-5 tỷ) obsess về future ("tài sản con cháu", "an nhàn hưu trí")
3. **Shareable** — Visualization của twin có thể viral trên FB/Zalo (Tết 2027 marketing moment)
4. **Sticky** — User check twin daily như check Strava/Fitbit avatar → daily hook
5. **Justifies premium pricing** — "Crystal ball cho tài chính"
6. **Leverages existing tech** — Phase 3.7 agent compute projections cheaply

### Tại sao pricing pivot xuống?

**Insight:** 149k/399k positioning compete với financial advisor (10-20tr/tháng), nhưng product không thay thế advisor được. → Should compete với **streaming services** mental category instead.

| Original (149/399) | New (68/168) | Implication |
|--------------------|--------------|-------------|
| Premium niche | Mass affluent volume | Need 6-7x users for same revenue |
| Compete với advisor | Compete với Spotify (199k Family) | Different mental category |
| Must-have product | Nice-to-have OK | Less pressure on every feature |
| LTV high, CAC justify | LTV moderate, CAC strict | Marketing efficiency critical |

68k = "2 ly cafe" → impulse purchase. 168k < Spotify Family → safe mental anchor.

**Cost analysis at 68k Pro:**
- Phase 3.7 agent cost: ~$0.0006/query average
- Heavy user (~500 queries/month) = ~$0.30 cost
- Profit margin: ~$2.7 USD/heavy user → economically viable

### Tại sao phased Twin (not full launch)?

Decided to split Twin into 3 sub-phases để de-risk:
- **Phase 4A (Conservative MVP):** Net worth projection 5/10 năm với probability cones
- **Phase 4B (Polish):** Better forecasts, predictions vs actual tracking, share images
- **Phase 7B (Life Sim):** Life event simulator, ship at Tết 2027

**Rationale:** Conservative version = predictions cẩn thận, ít risk. Test market trước khi invest in life simulator. User adoption shape v2 features (data-driven).

---

## 📊 What Changed Concretely

### Vision Statement
- **V2:** "Personal CFO for Vietnamese mass affluent"
- **V3:** "Personal CFO that shows you your financial future" (Twin emphasis)

### Pricing
- **V2:** Pro 149k / CFO 399k
- **V3:** Pro 68k / CFO 168k

### Roadmap Structure
- **V2:** Open-ended phase progression
- **V3:** 10-month plan với Tết 2027 launch target as North Star

### Trụ Cột (Pillars)
- **V2:** 3 pillars (Wealth, Cashflow, Investment)
- **V3:** 4 pillars (added "Future Vision" as 4th — the differentiator)

### Phase Sequencing
- **V2:** Phase 3B (Market Intelligence) was next after 3A
- **V3:** Phase 3.8 (Wealth Completion) inserted before 3.9 (Market Data); Phase 4 fundamentally redefined as Twin

### Peer Benchmarking Approach
- **V2:** Real peer data từ launch
- **V3:** Synthetic cohort initially → real peer post-Tết (chicken-and-egg solved)

---

## 🚫 What We Rejected

### Path X (Incremental polish)
**Rejected because:** No clear differentiation = competing on execution against incumbents với larger teams + budgets. Risk of being "yet another finance app."

### Premium-only pricing
**Rejected because:** 149k/399k caps user base too tight. Math: need 6-7x volume scale, but high CAC required. Volume play với 68k unlocks viral mechanics + lower CAC.

### Real peer data từ Day 1
**Rejected because:** Chicken-and-egg — at launch có 0 users → 0 cohort. Synthetic data từ market reports + assumptions là acceptable bridge.

### Single-number Twin predictions
**Rejected because:** "Tài sản 2030 của bạn: 5,234,567,890đ" sets expectation of exactness → 1 năm sau lệch → trust gone. **Probability cones** với honest framing là better.

---

## ⚠️ Risks Acknowledged

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Twin predictions inaccurate at launch | Medium | High | Probability cones + transparency framing |
| Peer data insufficient for Tết launch | Medium | Medium | Synthetic cohort fallback ready |
| User base growth slower than expected | High | High | Soft launch June + iterate before Tết |
| Implementation slip beyond Tết | Low | High | 3-4 day/phase velocity (Claude Code), buffer in roadmap |
| Pricing too low for revenue targets | Medium | Medium | Volume strategy, can add CFO+ tier later |
| Competitive response (MISA add AI) | Medium | Medium | Twin moat unique, hard to replicate fast |

---

## 📅 Timeline Implications

**10-month roadmap to Tết 2027:**

| Month | Milestone | Phase |
|-------|-----------|-------|
| May-June 2026 | Wealth completion + Market data | Phase 3.8 + 3.9 |
| **June 2026** | 🎉 **Soft launch** | — |
| Jul-Sep 2026 | Twin built (Conservative + Polish) | Phase 4A + 4B |
| Oct-Nov 2026 | Behavioral + Household | Phase 5 + 6 |
| Dec 2026 | Tết features pre-built | Phase 7A |
| **Feb 2027** | 🎆 **TẾT BÙNG NỔ** marketing | Phase 7B |
| Mar 2027+ | Scale (PWA, Zalo Mini) | Phase 8+ |

---

## 🎯 Success Metrics (V3)

### Pre-launch (June 2026)
- Phase 3.7 agent ≥90% query success
- Phase 3.8 features all functional
- 50+ early users by end of June

### Pre-Tết (Oct-Dec 2026)
- ≥1000 active users
- Twin engagement: ≥40% daily check
- Net worth tracked >500tr average

### Tết 2027 launch
- Pricing conversion: 5-10% Free→Pro
- Pro→CFO upsell: 10-15%
- D7/D30 retention: 70%/50%
- NPS: ≥50

### Year 1 post-Tết
- 10K+ active users
- ARR: 5-10 tỷ VND
- Public PR moments (TechCrunch VN, etc.)

---

## 🔄 What Needs to Change in Code

This pivot affects strategy + roadmap, NOT existing code architecture. Phase 3.7 agent foundation remains correct và reusable cho Phase 4 (Twin):

- ✅ 3-tier orchestrator → reused by Twin tools
- ✅ Tool registry pattern → Twin = new tools
- ✅ Streaming → Twin updates progressive
- ✅ Multi-tenancy → unchanged
- ✅ Database models → Phase 3.8 extends, not replaces

→ V2 → V3 pivot is **strategic, not technical**. Existing investments preserved.

---

## 📚 References

- **Original strategy V1:** [strategy-v1.md](./strategy-v1.md) — original "Finance Assistant" concept (if exists)
- **Strategy V2:** [strategy-v2.md](./strategy-v2.md) (archived in this folder)
- **Previous migration (V1→V2):** [MIGRATION_NOTES_V1_V2.md](./MIGRATION_NOTES_V1_V2.md) (renamed from MIGRATION_NOTES.md)
- **Current strategy (V3):** [strategy.md](../current/strategy.md)
- **Phase 3.8 detailed plan:** [phase-3.8/detailed.md](../current/phase-3.8/detailed.md)
- **Phase 3.8 issues:** [phase-3.8/issues.md](../current/phase-3.8/issues.md)
- **Phase 3.8 test cases:** [phase-3.8/test-cases.md](../current/phase-3.8/test-cases.md)

---

## 🧠 Lessons for Future Pivots

1. **Pricing positioning matters as much as features** — 149k vs 68k is not just amount, it's mental category (advisor vs streaming).

2. **Differentiation > polish when category is crowded** — Vietnamese personal finance space has many tracking apps. Twin creates new category.

3. **Phased de-risking** — Don't ship full vision at once. Conservative MVP → Polish → Premium = ability to iterate based on data.

4. **Honest framing builds trust** — Probability cones over single numbers. "Có thể" over "sẽ". Show predictions vs actual.

5. **Existing investments compound** — Phase 3.7 agent built for Phase 3.5 queries works for Phase 4 Twin too. Good architecture survives strategy pivots.

6. **Vietnamese cultural moments are leverage** — Tết = unique launch opportunity. Năm mới Bé Tiền mới framing.

---

**Adopted by:** Phuong (founder)  
**Date:** May 2026  
**Status:** ✅ Active strategy as of V3 promotion
