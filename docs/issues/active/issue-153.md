# Issue #153

[Bug] Monthly report advice section không phù hợp với định hướng Personal CFO và data thực tế của user HNW

## Bug Report

### Mô tả lỗi
Sau khi sản phẩm chuyển định hướng sang **Personal CFO cho Mass Affluent / HNW**, phần **"Điểm chính" và "Lời khuyên"** cuối báo cáo tháng vẫn đang generate theo logic cũ — giống một finance app cho người chưa có tài sản, không phải CFO advisor cho người có 120 tỷ+ tài sản.

---

## Ví Dụ Lỗi Thực Tế

**User:** HNW, tài sản >120 tỷ

**Bot trả lời (SAI):**
```
### ✅ Điểm chính:
- Bạn đã đầu tư mạnh (20 triệu) – đây là khoản chi lớn nhất...
- Chi tiêu ăn uống rất thấp (170k) – có thể bạn đã ăn ở nhà...
- Thu nhập và tiết kiệm chưa được ghi nhận.

### 💡 Lời khuyên:
1. 📝 Ghi lại thu nhập ngay – để biết bạn đang lời hay lỗ trong tháng.
2. ⚖️ Cân nhắc tỷ lệ đầu tư – 20 triệu/tháng là rất lớn nếu thu nhập chưa rõ...

Bạn muốn mình nhắc nhở cuối tháng để cập nhật thu nhập không? 😊
```

**Tại sao sai:**
- Comment "20 triệu/tháng là rất lớn" với user có 120 tỷ tài sản là **vô nghĩa và sai context** hoàn toàn
- Suggest "ghi lại thu nhập để biết lời/lỗ" — không phù hợp với HNW user, họ cần **cashflow analysis, tỷ lệ đầu tư/tài sản, runway**, không phải biết "có lời không"
- Nhận xét "ăn uống thấp vì ăn nhà" là **phỏng đoán sai context** — với HNW, ăn uống 170k/tháng là outlier cần context, không phải compliment
- Tone của lời khuyên giống app dành cho người mới đi làm (Level 0 Starter), không phải CFO advisor

---

## Root Cause

Hệ thống đang dùng **prompt/logic tạo lời khuyên cũ** không nhận biết:
1. **Wealth level của user** (Starter vs HNW → lời khuyên khác hoàn toàn)
2. **Context tài sản thực tế** (120 tỷ tài sản → 20tr đầu tư = 0.016% tài sản, không đáng "cảnh báo")
3. **Định hướng Personal CFO** — focus vào net worth growth, allocation, cashflow optimization — không phải budget control

---

## Expected Behavior (theo strategy.md)

Với user HNW (tài sản >1 tỷ, trong case này >120 tỷ), phần insight sau báo cáo phải:

**Về Điểm chính:**
- Frame 20tr đầu tư trong context tổng tài sản (ví dụ: "chiếm 0.02% tổng tài sản")
- Nhận xét về **allocation strategy**, không phải budget
- Nêu **dữ liệu thiếu có ý nghĩa** (thu nhập, passive income từ tài sản) thay vì nói chung chung "chưa khai báo"

**Về Lời khuyên:**
- **Không** suggest "cân nhắc tỷ lệ đầu tư vì thu nhập chưa rõ" với HNW user
- Thay bằng: phân tích tỷ lệ đầu tư/tổng tài sản, gợi ý hoàn thiện data (thu nhập thụ động từ BĐS, cổ tức, lãi)
- Gợi ý **portfolio rebalancing** nếu cần
- Nhắc về **mục tiêu mua xe đang 0%** — hỏi user có muốn allocate từ tài sản hiện có không

**Về Tone:**
- HNW level → tone của CFO advisor, không phải app nhắc nhở sinh viên
- Không hỏi "nhắc cuối tháng để ghi thu nhập" — thay bằng **action-oriented CFO prompt**

---

## Acceptance Criteria

- [ ] Phần insight sau báo cáo tháng phải nhận biết **wealth level** của user và adapt accordingly
- [ ] Với user HNW (>1 tỷ tài sản): lời khuyên phải frame trong context tổng tài sản, không comment tuyệt đối ("20tr là rất lớn")
- [ ] Logic tạo insight phải sync với **data thực tế của user**: tài sản hiện có, income streams đã khai báo, goals đang active
- [ ] Không đưa ra lời khuyên dựa trên dữ liệu thiếu mà không acknowledge sự thiếu đó một cách CFO-appropriate
- [ ] Tone phải match wealth level: Starter = encouraging + educational, HNW = CFO advisor + strategic
- [ ] Mục tiêu active (ví dụ: mua xe 50tr) phải được reference với context tài sản — với HNW, 50tr target là trivial và bot nên acknowledge điều đó

---

## Scope of Fix

| Component | Action |
|-----------|--------|
| Prompt tạo "Điểm chính" | Thêm wealth-level context + asset breakdown |
| Prompt tạo "Lời khuyên" | Rewrite theo 4 levels trong strategy.md |
| Data injection vào prompt | Thêm: total net worth, wealth level, income streams, asset breakdown |
| Goal analysis | Frame target amount vs total assets, không chỉ vs chi tiêu |
| Closing CTA | Thay bằng CFO-style action items phù hợp level |

---

## Reference
- `docs/current/strategy.md` — Section "Ladder of Engagement" (4 levels)
- `docs/current/strategy.md` — Section "3 Tier Expense Tracking"
- `docs/current/strategy.md` — Section "Positioning Shift: Finance Assistant → Personal CFO"
- Phase 3.5 #126 — Wealth-level adaptive responses

## Priority
🔴 **Critical** — Đây là bug về product positioning. Lời khuyên sai context với HNW user phá vỡ hoàn toàn giá trị của Personal CFO product.
