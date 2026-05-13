# Migration V1 → V2: Finance Assistant → Personal CFO

**Date:** 24/04/2026  
**Decision maker:** Phuong

---

## What Changed

### Positioning
- **V1:** "Finance Assistant" — giúp người Việt theo dõi chi tiêu tốt hơn
- **V2:** "Personal CFO" — AI assistant quản lý toàn bộ tài sản cho tầng lớp trung lưu Việt Nam

### Target User
- **V1:** Gen Z / Millennials (22-35 tuổi) đang học quản lý chi tiêu
- **V2:** Mass affluent (30-50 tuổi) có tài sản 200tr - 10 tỷ, cần tool quản lý wealth

### Core Value Prop
- **V1:** "Ghi chép chi tiêu không cần nhập tay"
- **V2:** "Nhìn thấy tổng tài sản hàng ngày, ra quyết định tài chính đúng"

### Phase 3 Scope
- **V1:** Zero-Input Philosophy — SMS parsing, OCR, Voice, Location (5 layers capture)
- **V2:** Split thành 3A + 3B:
  - **3A (Wealth Foundation):** Asset tracking, net worth, morning briefing, simple storytelling
  - **3B (Market Intelligence):** Real-time prices, news, bank rates (outline only cho đến khi 3A validate)

### Pricing
- **V1:** Freemium với Pro 99k/tháng
- **V2:** Freemium → Pro 149k/tháng → CFO 399k/tháng (tier cao với wealth management đầy đủ)

---

## Why We Pivoted

### Insight 1: "Báo cáo tổng tài sản" là core value thực sự
User đã implement morning briefing về tổng tài sản (7h sáng hàng ngày). Khi bàn sâu, nhận ra đây là **North Star feature**, không phải expense tracking. Mọi thứ khác chỉ là supporting.

### Insight 2: Market gap rõ ràng ở VN
- MISA / Money Lover: Serve người chưa có tài sản (<50tr)
- Finhay / Tikop: Single-asset investment apps
- Private banking: Chỉ serve >10 tỷ
- **Gap rộng:** Người có 200tr - 5 tỷ → không ai serve. Đây là segment bạn nhắm đến.

### Insight 3: AI-native moat mạnh hơn
Storytelling-based data giàu hơn SMS parsing (có emotion, context, social signals). Kiến trúc AI-first không thể bắt chước bằng việc thêm AI vào expense tracker.

### Insight 4: Ladder of Engagement
User 22 tuổi chưa có tài sản vẫn có thể dùng — net worth = 10tr tiền mặt vẫn hiển thị. App grow cùng user qua 4 levels (Starter → Young Prof → Mass Affluent → HNW). Đây là **LTV moat** — đối thủ chỉ serve 1 segment.

### Insight 5: Monetization justify pricing cao
"Personal CFO" framing cho phép pricing 10x cao hơn "expense tracker". User trung lưu sẵn lòng trả 399k/tháng cho wealth management, nhưng không trả 99k cho expense tracker.

---

## What We Kept

### Phases Unchanged
- **Phase 1 (UX Foundation)** — Rich messages, inline buttons, Mini App, visual identity
- **Phase 2 (Personality & Care)** — Onboarding, memory moments, empathy, surprise & delight

### Concepts Kept
- **AI Storytelling** — moved to Phase 3A nhưng đã simplified (threshold-based, không track mọi giao dịch)
- **OCR + Voice capture** — supplementary cho storytelling, vẫn có
- **Personality & empathy** — càng quan trọng hơn khi deal với wealth data
- **Vietnamese-specific content** — Tết, Trung thu, seasonal events

---

## What We Dropped

### Abandoned Features
- **SMS forwarding strategy** — was Phase 3 core, giờ không cần vì storytelling-first
- **Email forwarding** — không match với positioning mới
- **5-layer capture architecture** — over-engineered cho use case hiện tại
- **iPhone-specific strategy** — became redundant khi Personal CFO positioning không phụ thuộc platform

### Archived Docs
- `strategy-v1.md` — original "finance assistant" strategy
- `phase-3-detailed-v1.md` — original Zero-Input Philosophy implementation

---

## Key Decisions Locked In

1. ✅ **Positioning: Personal CFO cho mass affluent VN**
2. ✅ **Target: 30-50 tuổi, tài sản 200tr - 10 tỷ** (với ladder xuống Starter cho người trẻ)
3. ✅ **Expense tracking: Threshold-based, không exhaustive** (<200k gộp, 200k-2tr storytelling, >2tr active capture)
4. ✅ **Phase 3 chia thành 3A + 3B** — 3A ship trước, 3B chỉ build sau khi validate
5. ✅ **Ownership model: Case A (ở) + Case C (đầu tư) trong Phase 3A**, Case B (rental) trong Phase 4
6. ✅ **Market data sources:** SSI/VNDIRECT cho stocks, CoinGecko cho crypto, SJC scraping cho gold, user-input cho BĐS

---

## References

### Active Documents
- [Product Strategy V2](../current/strategy.md)
- [Phase 3A Detailed](../current/phase-3a-detailed.md)
- [Phase 3B Outline](../current/phase-3b-outline.md)
- [Phase 3A Issues](../current/phase-3a-issues.md)

### Archived Documents
- [Strategy V1](v1-finance-assistant/strategy-v1.md)
- [Phase 3 V1 Detailed](v1-finance-assistant/phase-3-detailed-v1.md)

### Discussion Context
- Pivot discussed: 24/04/2026
- Validation plan: 7-user testing trong Phase 3A Week 4
- Next review: Sau khi Phase 3A ship, đánh giá retention + user feedback

---

**Note:** Nếu 3 tháng nữa product lại pivot, **tạo file migration mới** (không xóa file này). Documentation evolution là document story của product. 💚
