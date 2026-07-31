# MIGRATION NOTES: Strategy V3 → V4

> **Loại document:** ADR (Architecture Decision Record) for product strategy pivot
> **Ngày tạo:** 05/07/2026
> **Status:** ✅ Adopted
> **Triggered by:** Soft-launch retro tháng 6/2026 — cohort data (admin dashboard) + feedback tổng hợp Founding Members

---

## 📌 Context

Tháng 6/2026 chúng ta chạy soft launch theo đúng kế hoạch V3: Founding Members cohort, Twin là differentiator, target Level 1-2 (Young Pro + Mass Affluent), volume play 68k/168k, hướng tới Tết 2027.

Sau ~6 tuần, hai nguồn dữ liệu buộc phải nhìn lại toàn bộ approach:

### 1. Cohort data (admin dashboard, đọc ngày 05/07/2026)

| Signal | Kế hoạch V3 | Thực tế |
|---|---|---|
| Cohort size | 50 founding members | **~23 users** (weekly cohorts 11/05 → 22/06: 3, 1, 1, 4, 1, 12, 1) |
| Wealth level phân bố | Tập trung Level 1-2 (30tr – 3 tỷ) | **100% Level 0 (Khởi Đầu / Starter)** — không một user nào trong target segment |
| Trạng thái hoạt động | D7 ≥ 40%, Twin daily check ≥ 40% | **Gần như toàn bộ Dormant**; 1 At-risk; nhiều user "Chưa hoạt động" (0 tin nhắn — chưa từng kích hoạt sau khi được mời) |
| Mức độ dùng | Habit loop hàng tuần | Top user 92 tin nhắn (từ 15/05); kế tiếp 20, 18, 10, 8… — phần lớn 1-2 tin nhắn |
| Kill §1 (D28 < 20%) | Không trip | **Tripped/near-tripped**: các cohort ≥ 28 ngày tuổi (~9-10 users) gần như không có hoạt động trong 7 ngày gần nhất |
| Kill §2 (cost > 50k/user) | Không trip | An toàn tuyệt đối: $0.0005–$0.0062/user LLM cost |
| Revenue | 0 (đúng kế hoạch, free phase) | 0 |

**Lưu ý đọc số:** heatmap retention hiển thị % trông ổn (67-75% W1-W2) nhưng denominators quá nhỏ (n = 1-4). Tín hiệu thật duy nhất là cohort 15/06 (12 users, 75% W1-W2) — nhưng cohort này chưa đủ tuổi để đo D28. Không được lấy % đẹp trên mẫu nhỏ làm bằng chứng PMF.

### 2. Feedback tổng hợp (5 nguồn)

- **Hoàng Đại Cường (Vietcap, senior — đại diện chính xác cho Mass Affluent V3 target):** từ chối toàn bộ model — không có thời gian nhập liệu tay, Telegram không hợp với người nhiều tiền, khách hàng giàu không đi tìm AI để quản lý tiền, bot fail một số query, "quan trọng là niềm tin".
- **Long Nguyễn (VMCG Capital):** con số Twin không thuyết phục ("2 năm tăng 10%; 10 năm không nổi x2") — có thể do thiếu data đầu vào; đề xuất bắt nhập đủ data trước khi cho xem Twin; khuyên **thu hẹp tệp khách, chọn ngách** thay vì làm app cho tất cả mọi người.
- **Nhóm sinh viên mới đi làm:** thích tách nguồn thu nhập, đa dạng tài sản, biểu đồ; **chưa tin lời khuyên Twin**; muốn persona tùy chỉnh (kể cả mode "chửi" khi tiêu hoang).
- **Chị Nhung Lê (thu nhập ổn định, chuẩn bị lập gia đình):** goal-splitting hữu dụng, dự đoán "hợp lý ở mức cơ bản"; đề xuất **quản trị rủi ro**: "nếu phải chi 100tr viện phí thì rút từ tài sản nào ít ảnh hưởng tương lai nhất, và danh mục sau đó thay đổi ra sao?"
- **Hà Châu (chủ shop):** quản lý dòng tiền lắt nhắt tốt; muốn **xuất Excel/Google Sheets**.

### Tổng hợp chẩn đoán

1. **Sai segment.** Demand thực nằm ở Level 0-1 (người trẻ đang xây tài sản); Mass Affluent — chính người đại diện segment đó — từ chối model từ gốc (kênh, ma sát nhập liệu, niềm tin vào AI). Cohort thực tế 100% Starter xác nhận bằng số.
2. **Twin bị đóng khung sai.** Mọi feature-ask trong feedback (shock sim, plan-to-goal, cảnh báo tiêu hoang, cảnh báo lừa đảo) đều là **decision moment** — người dùng muốn hỗ trợ ra quyết định tại thời điểm quyết định, không muốn một bức tranh dự báo thụ động để ngắm mỗi ngày.
3. **Vòng lặp tự hại niềm tin.** First-5-Minutes WOW → data đầu vào mỏng → forecast không thuyết phục ("10 năm không nổi x2") → mất niềm tin → không quay lại nhập thêm data. V3 không có cơ chế thoát vòng lặp này.

---

## 🎯 Decision

**Adopted Strategy V4 — "Decision Engine":**

1. **Cắt hẳn Mass Affluent (Level 2+) khỏi target trực tiếp.** Target mới: **22-35 tuổi, từ khoản lương đầu tiên đến ~500tr tài sản** (Level 0 → Level 1) — "thế hệ đang xây". Đường tới người giàu hơn (nếu có) đi qua B2B2C cobranding với quỹ/CTCK/ngân hàng — track exploratory, không cam kết roadmap.
2. **Reframe Twin: Future Vision → Decision Engine ("GPS tài chính").** Twin không còn là bức tranh để ngắm; nó là engine trả lời 4 loại decision moment: shock simulation + liquidation advice, plan-to-goal feasibility, drift/overspend warning gắn hậu quả Twin, scam red-flag check.
3. **Confidence meter ("độ nét") thay cho forced data entry.** Data completeness trở thành habit mechanic: nhập thêm → tương lai "nét" hơn — thay vì bắt nhập đủ trước khi dùng (giết funnel) hoặc forecast tự tin trên data mỏng (giết niềm tin).
4. **Monetization: paywall decisions, không paywall tracking.** Tracking free vĩnh viễn; anchor 68k giữ nguyên; affiliate hoãn ≥ 12 tháng để giữ neutrality làm moat.
5. **GTM chuyển kênh:** rời các community tài chính chuyên nghiệp → TikTok / KOL tài chính trẻ / kênh sinh viên–người mới đi làm.
6. **North star đổi:** từ "net worth tracked > 500tr/user" + Twin daily check → **weekly decision interactions per active user + D28 retention**.

Cả 2 quyết định gate (cắt Mass Affluent, chuyển Decision Engine) được founder approve ngày 05/07/2026.

---

## 🤔 Reasoning

### Tại sao cắt Mass Affluent thay vì sửa cách tiếp cận họ?

- **Bằng chứng hành vi > lời nói:** kênh acquisition tự nhiên (bạn bè, community tài chính) chỉ mang về Level 0. Người Level 2+ duy nhất thử sản phẩm (Cường) từ chối cả 3 tầng của model: kênh Telegram, ma sát nhập liệu, và ý tưởng "tìm AI để quản lý tiền".
- **Trust là chi phí cố định khổng lồ với người giàu:** họ đòi hỏi thương hiệu/pháp lý/con người — những thứ một sản phẩm solo-founder giai đoạn này không thể mua được. Người trẻ đang xây tài sản có trust bar thấp hơn và gắn bó dài hơn (LTV theo thời gian: user 25 tuổi hôm nay là mass affluent 2032 — grow **with** your money).
- **Twin phù hợp nhất với người đang xây:** quỹ đạo từ 50tr → 500tr thay đổi rõ rệt theo hành vi hằng tháng; quỹ đạo của người đã có 3 tỷ phụ thuộc thị trường nhiều hơn hành vi — ít chỗ cho decision support tạo khác biệt.

### Tại sao Decision Engine thay vì Future Vision?

- **Người dùng đã bỏ phiếu bằng feature request:** 100% các đề xuất trong feedback là câu hỏi dạng quyết định ("nên rút từ đâu", "làm gì để đạt X", "cảnh báo khi tôi sắp làm sai"). Không ai xin thêm chart dự báo.
- **Passive prediction không tạo habit:** V3 đặt cược "user check Twin daily như Strava" — cohort data phủ nhận (dormancy gần toàn bộ, kể cả sau Phase 4.3 habit loop). Quyết định tài chính thì xảy ra liên tục trong đời thật — đó mới là trigger tự nhiên.
- **~70% năng lực đã build sẵn:** Life Event Simulator (Phase 4B) đã inject shock vào Monte Carlo paths. Cái thiếu là (a) entry conversational ("nếu tôi phải chi 100tr…"), (b) lớp liquidation advice (rút từ tài sản nào), (c) framing. Đây là pivot về **định vị + bề mặt sản phẩm**, không phải rebuild engine.
- **Trả lời đúng câu hỏi niềm tin:** một dự báo 10 năm rất khó tin; một câu trả lời "phương án A ít tổn thương tương lai hơn phương án B, vì…" kiểm chứng được ngay bằng logic — niềm tin xây qua từng quyết định nhỏ.

### Tại sao "độ nét" thay vì bắt nhập đủ data (đề xuất của Long)?

Đề xuất forced-entry chẩn đúng bệnh (forecast trên data mỏng phá niềm tin) nhưng kê sai thuốc: cohort hiện tại đã rơi ngay từ onboarding nhẹ (nhiều user 0-2 tin nhắn) — dựng thêm tường data chỉ chuyển điểm rơi sớm hơn. Giải pháp V4: **thành thật về độ mờ** ("ảnh tương lai của bạn đang nét 40% — thêm thu nhập + khoản tiết kiệm để nét hơn") và để mỗi lần nhập thêm data trả thưởng bằng độ nét + câu trả lời quyết định tốt hơn. Data completeness từ chỗ là điều kiện tiên quyết trở thành chính habit loop.

### Tại sao paywall decisions, không paywall tracking?

- Tracking là commodity (Money Lover, MISA, Excel đều làm được) — thu phí thứ ai cũng có là tự sát với segment 22-35.
- Decision support là thứ duy nhất trên thị trường VN chưa ai làm — giá trị cảm nhận rõ tại đúng khoảnh khắc đau (sắp mất tiền, sắp quyết định lớn).
- Free tracking vĩnh viễn = máy tạo data → decisions càng nét → willingness-to-pay tăng theo thời gian dùng.

### Tại sao hoãn affiliate ≥ 12 tháng?

Scam check + liquidation advice chỉ có giá trị nếu Bé Tiền **không ăn hoa hồng từ bất kỳ sản phẩm tài chính nào**. Neutrality là moat mà các app gắn với quỹ/sàn không thể copy. Bật affiliate sớm phá moat này vĩnh viễn.

---

## 📊 What Changed Concretely

| | V3 | V4 |
|---|---|---|
| Vision | "Personal CFO cho mass affluent — nhìn thấy tương lai tài chính" | "GPS tài chính cho thế hệ đang xây tài sản — ra quyết định đúng tại thời điểm quyết định" |
| Internal shorthand | Personal CFO | **Decision Engine** (retire "Personal CFO" cả internal) |
| Target | Level 1-2 (30tr – 3 tỷ), Household mode phase 5.6 | **22-35 tuổi, Level 0 → 1 (0 – 500tr)**; Level 2+ chỉ qua B2B2C exploratory; Household parked |
| Differentiator | Twin = Future Vision (probability cones, daily check) | Twin = **Decision Engine** (4 decision moments); cones là backend, không phải sản phẩm |
| Data strategy | First-5-Minutes WOW, data sau | **Confidence meter "độ nét"** — progressive reveal, data completeness = habit mechanic |
| Monetization | Pro 68k / CFO 168k gate theo tier feature | Free tracking forever; **paywall decision interactions**; anchor 68k giữ; tier "CFO" 168k re-validate sau |
| Revenue phụ | (chưa định) | Affiliate **hoãn ≥ 12 tháng** — neutrality moat |
| GTM | Bạn bè + community tài chính + Zalo primary Tết 2027 | **TikTok / KOL trẻ / sinh viên–mới đi làm**; Zalo re-evaluate post-Tết |
| North star | Net worth tracked > 500tr/user; Twin ≥ 40% daily check | **Weekly decision interactions/active user + D28 retention** |
| Kill criteria | §1-§7 (phase-4.1) | §1/§5/§7 recalibrate theo cohort mới + thêm decision-adoption + scam-check red line (xem strategy V4) |
| Roadmap kế tiếp | Phase 5.0 Encryption → Zalo 5.1-5.3 | **Phase 4.5 Decision Engine Foundation → 4.6 Onboarding Reset → 4.7 Guardian**; Encryption lùi sau; Zalo/Household/Badges parked |

**Giữ nguyên (carry-forward, non-negotiable):**
- Founding Members: 50% lifetime discount — ~23 slots đã dùng, các slot còn lại dành cho cohort segment mới.
- Customer-facing language rule: không "CFO" trong mọi user-facing text; Bé Tiền = *người đồng hành quản lý tài sản*.
- Bé Tiền persona floor: warm, không phán xét — tone dial cho phép "nghiêm khắc/thẳng thắn" theo yêu cầu user, không bao giờ sỉ nhục.
- Probability-over-precision, trust-through-transparency.
- Tết 2027 vẫn là marketing moment — nhưng có gate điều kiện (xem strategy V4).

---

## 🚫 What We Rejected

### Bắt nhập đủ data trước khi cho dùng Twin (đề xuất Long Nguyễn)
**Rejected:** cohort rơi ngay ở onboarding nhẹ; dựng tường data làm điểm rơi sớm hơn. Thay bằng độ nét + progressive reveal (đạt cùng mục tiêu accuracy mà không giết funnel).

### Cobranding ngay để giải bài toán trust (đề xuất trong feedback doc)
**Deferred (không reject hẳn):** đúng hướng cho Level 2+ nhưng sai thời điểm — chưa có PMF thì không có leverage đàm phán; deal B2B2C ăn 6-12 tháng bandwidth của solo founder. Giữ làm exploratory track, chỉ mở khi cohort mới chứng minh D28.

### Scam check kiểu phán quyết ("kèo này lừa đảo")
**Rejected:** rủi ro pháp lý + uy tín không chịu nổi 1 lần sai. V4 chỉ làm **red-flags + hướng dẫn tự kiểm chứng** ("kèo này có 4/6 dấu hiệu thường gặp ở scam; đây là cách tự kiểm tra…"), không bao giờ verdict.

### Đè tiếp vào cohort dormant để "cứu" retention
**Rejected làm ưu tiên chính:** cohort cũ sai segment từ gốc; chi phí hồi sinh > chi phí acquire đúng người. Làm 1 đợt re-engagement khi Phase 4.5 ship (decision features là lý do quay lại chính đáng), sau đó đo mọi thứ trên cohort mới.

### Mode "chửi" user theo nghĩa đen (đề xuất nhóm sinh viên)
**Rejected nguyên bản, adopted tinh thần:** tone dial cho phép mức "nghiêm khắc/thẳng thắn" — giữ persona floor không sỉ nhục, không phán xét (kill criterion §4 vẫn hiệu lực).

### Bỏ Telegram / build native app ngay
**Rejected:** vấn đề không nằm ở kênh với segment 22-35 (Telegram quen thuộc); native app chỉ khi PMF proven (nguyên tắc V3 giữ nguyên).

---

## ⚠️ Risks Acknowledged

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| n quá nhỏ (23 users, 5 nguồn feedback) — pivot trên mẫu yếu | Medium | High | V4 thiết kế để falsify nhanh: decision-adoption metric sau 6 tuần Phase 4.5; không chi tiền marketing trước khi gate qua |
| WTP của segment 22-35 thấp → paywall decisions không convert | Medium | High | Free tracking giữ funnel; test paywall tháng 11 với kill line < 3% conversion; giá trị decision tăng theo tài sản user (grow with money) |
| Scam check sai 1 lần → thiệt hại uy tín không hồi phục | Low-Med | Very High | Red-flags only, never verdict; disclaimer tự kiểm chứng; kill switch tức thì (red line trong kill criteria V4) |
| Liquidation advice bị đọc là "tư vấn đầu tư" (pháp lý) | Medium | High | Framing "phân tích kịch bản trên chính danh mục của bạn", không recommend sản phẩm bên ngoài; rà soát wording với legal trước ship |
| GTM TikTok/KOL nằm ngoài kỹ năng hiện tại của founder | High | Medium | Bắt đầu organic (build-in-public, seed nhóm sinh viên đã có); KOL chỉ sau khi D28 cohort mới ≥ 25% |
| Cohort 15/06 (12 users — tín hiệu tốt duy nhất) nguội trong lúc build 4.5 | Medium | Medium | Quick wins ship trước (export, tone dial) + re-engagement khi 4.5 ship |

---

## 📚 References

- **Strategy V3:** [strategy-v3.md](./strategy-v3.md) (archived)
- **Previous migration (V2→V3):** [MIGRATION_NOTES_V2_V3.md](./MIGRATION_NOTES_V2_V3.md)
- **Current strategy (V4):** [strategy.md](../current/strategy.md)
- **Soft-launch runbook (đã chạy):** [soft-launch-runbook.md](../current/soft-launch-runbook.md)
- **Kill criteria Phase 4.1 (đã trip §1):** [kill-criteria.md](../current/phase-4.1/kill-criteria.md)
- **Founding promise:** [founding-promise.md](../current/founding-promise.md)
- **Feedback nguồn:** file tổng hợp Founding Members 06/2026 (offline doc, tóm tắt trong Context ở trên)

---

## 🧠 Lessons for Future Pivots

1. **Segment được chứng minh bằng ai xuất hiện, không phải ai được nhắm.** 100% cohort là Level 0 trong khi target là Level 1-2 — dữ liệu acquisition tự nó là kết quả nghiên cứu thị trường.
2. **% retention trên mẫu nhỏ là ảo giác.** Heatmap 75% với n=4 đẹp hơn thực tế "gần như toàn bộ dormant". Luôn nhìn số tuyệt đối cạnh %.
3. **Feature request của user là data về job-to-be-done, không phải backlog.** Cả 5 nguồn feedback xin cùng một thứ dưới 5 hình dạng: hỗ trợ quyết định. Đọc pattern, đừng đọc từng request.
4. **Kill criteria chỉ có giá trị nếu dám kích hoạt.** §1 trip → V4 chính là action plan Day 1-7 của §1 (pivot positioning). Viết trước, làm theo — đó là lý do viết.
5. **WOW nhanh và forecast đáng tin mâu thuẫn nhau nếu không có cơ chế trung gian.** "Độ nét" là cơ chế hòa giải: thành thật về uncertainty ngay từ đầu, thưởng cho việc làm rõ dần.
6. **Engine build rồi có thể tái định vị rẻ hơn nhiều so với build mới.** Monte Carlo + Life Event Sim giữ nguyên; thứ thay đổi là câu hỏi mà engine trả lời.

---

**Adopted by:** Phuong (founder)
**Date:** 05/07/2026
**Status:** ✅ Active strategy as of V4 promotion
