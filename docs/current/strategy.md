# Bé Tiền — Product Strategy V4 ("Decision Engine")

> **Phiên bản thứ 4 của strategy, sau soft launch tháng 6/2026.**
> V4 là kết quả của soft-launch retro: cohort data (admin dashboard) + feedback Founding Members buộc pivot cả 3 trục — segment, sản phẩm, business. Full rationale: [MIGRATION_NOTES_V3_TO_V4.md](../archive/MIGRATION_NOTES_V3_TO_V4.md). V3 archived tại [strategy-v3.md](../archive/strategy-v3.md).

---

> ⚠️ **Customer-facing language rule (NON-NEGOTIABLE — carried từ V3, mở rộng).**
> - "Personal CFO" **retired hoàn toàn** — kể cả internal shorthand. Internal positioning V4 là **"Decision Engine"**.
> - "CFO", "Decision Engine", "GPS tài chính" (như tên chức năng) KHÔNG xuất hiện trong user-facing text — welcome bubbles, briefings, chart watermarks, share images, announcement copy, support replies.
> - Với user, Bé Tiền là **người đồng hành quản lý tài sản** — ấm, đơn giản, không corporate. Reviewer enforce rule này trên mọi user-facing change.

---

## 📊 Soft Launch tháng 6/2026 — Sự thật phải nhìn thẳng

Nguồn: admin dashboard (đọc 05/07/2026) + feedback tổng hợp 5 nguồn. Chi tiết đầy đủ trong [migration notes](../archive/MIGRATION_NOTES_V3_TO_V4.md).

| V3 đặt cược | Thực tế |
|---|---|
| 50 founding members | **~23 users** (7 weekly cohorts: 3, 1, 1, 4, 1, 12, 1) |
| Target Level 1-2 (30tr – 3 tỷ) | **100% cohort là Level 0 (Khởi Đầu)** — không một user nào trong target |
| Twin daily check ≥ 40%, D7 ≥ 40% | Gần như toàn bộ **Dormant**; nhiều user chưa từng kích hoạt (0 tin nhắn); top user 92 msgs, phần lớn 1-2 msgs |
| Kill §1 (D28 ≥ 20%) an toàn | **§1 tripped**: cohorts ≥ 28 ngày (~9-10 users) gần như im lặng 7 ngày gần nhất |
| Mass Affluent sẽ đón nhận | Người L2+ duy nhất thử (senior Vietcap) từ chối toàn bộ model: kênh, ma sát nhập liệu, và ý tưởng tìm AI quản lý tiền |
| Cost là rủi ro | Cost không phải vấn đề: $0.0005–$0.0062/user/tháng (§2 an toàn tuyệt đối) |

Điểm sáng duy nhất: cohort 15/06 (12 users, 75% W1-W2 — chưa đủ tuổi D28) và các feature-request rất cụ thể từ user trẻ. **V4 xây trên hai điểm sáng đó.**

**V4 chính là action plan của kill criterion §1** — pivot positioning, không phải "thêm một tuần nữa".

---

## 🎯 Vision Statement (V4)

**Bé Tiền là GPS tài chính cho thế hệ Việt đang xây tài sản — giúp họ ra quyết định đúng tại đúng thời điểm quyết định, và lớn lên cùng tài sản của họ.** *(internal positioning — xem language rule ở trên)*

Không compete với Money Lover/MISA (tracking là commodity, free vĩnh viễn ở Bé Tiền). Không compete với Finhay/Tikop (không bán sản phẩm đầu tư — đó chính là moat). Category mới ở VN: **financial decision support** — engine mô phỏng + AI agent trả lời "tôi nên làm gì?" trên chính danh mục của user.

**Thesis dài hạn:** user 25 tuổi hôm nay là mass affluent 2032. Không đi tìm người giàu — **lớn lên cùng người sẽ giàu.**

---

## 👥 Target User V4 — Thu hẹp triệt để

**Target duy nhất: 22-35 tuổi, từ khoản lương đầu tiên đến ~500tr tài sản** (Level 0 → Level 1 — "thế hệ đang xây / tích sản").

Personas (từ chính cohort + feedback thật):
- **Người mới đi làm** có khoản nhỏ đầu tiên để đầu tư (nhóm sinh viên trong feedback)
- **Người chuẩn bị mốc đời lớn** — cưới, con, mua nhà (chị Nhung)
- **Người có dòng tiền tự doanh lắt nhắt** — chủ shop nhỏ, freelancer (Hà Châu)

Quyết định segment (approved 05/07/2026):
- ❌ **Mass Affluent (Level 2+) cắt khỏi target trực tiếp.** Không thiết kế feature, copy, hay GTM cho họ nữa.
- 🧪 **B2B2C cobranding** (quỹ/CTCK/ngân hàng đưa Bé Tiền vào hệ sinh thái của họ) = exploratory track, chỉ mở khi cohort mới chứng minh D28 — đây là đường duy nhất còn lại tới Level 2+.
- 🅿️ **Household mode parked** (match segment cũ, không phải segment mới).

Wealth ladder giữ nguyên làm hệ đo (Khởi Đầu → Đỉnh Cao), nhưng ladder giờ là **hành trình của một user theo thời gian**, không phải danh sách segment để nhắm song song.

---

## 🔑 The Differentiator V4 — Twin Decision Engine

> Twin không chết — Twin đổi nghề. Monte Carlo engine + Life Event Simulator (Phase 4A/4B) giữ nguyên làm backend. Thứ thay đổi là **câu hỏi mà engine trả lời**: từ "tương lai bạn trông thế nào?" (ngắm) → "bạn nên làm gì?" (quyết định).

### 4 Decision Moments

1. **🚨 Shock simulation + liquidation advice** *(ask trực tiếp của chị Nhung; ~70% engine đã có từ Phase 4B)*
   "Nếu em phải chi 100tr viện phí, rút từ đâu ít hại tương lai nhất?" → Bé Tiền so sánh các phương án rút trên chính danh mục user (tiết kiệm vs vàng vs cổ phiếu), show tác động lên quỹ đạo, khuyến nghị thứ tự — rồi vẽ lại danh mục sau cú sốc.
   *Guardrail:* phân tích kịch bản trên tài sản của chính user, KHÔNG recommend mua/bán sản phẩm bên ngoài (ranh giới pháp lý).

2. **🧭 Plan-to-goal feasibility** *(ask trong feedback: "100tr → 5 tỷ trong 10 năm, tôi nên làm gì?")*
   Trả lời thành thật bằng engine: khả thi hay không, cần điều kiện gì (tỷ suất, tiết kiệm/tháng), và các phương án thực tế gần nhất. **Dám nói "mục tiêu này gần như bất khả thi, nhưng 1.8 tỷ thì trong tầm tay nếu…"** — honesty là feature.

3. **📉 Drift warning** *(ask trong feedback: cảnh báo tiêu hoang)*
   Khi hành vi lệch kế hoạch, cảnh báo bằng **hậu quả Twin cụ thể** ("tháng này chi vượt 3tr — giữ nhịp này, mốc mua nhà 2029 lùi 14 tháng"), không phải lời mắng chung chung. Persona floor giữ nguyên: nghiêm khắc được (tone dial), sỉ nhục không bao giờ.

4. **🛡️ Scam check** *(ask trong feedback: cảnh báo kèo lừa đảo)*
   User dán một "kèo đầu tư" → Bé Tiền đối chiếu **red-flags** (lãi cam kết phi thực tế, mô hình đa cấp, không pháp nhân…) + hướng dẫn tự kiểm chứng.
   **Red line tuyệt đối: chỉ red-flags + cách tự kiểm tra, KHÔNG BAO GIỜ verdict "đây là lừa đảo / đây là an toàn".** Một verdict sai = chết uy tín + rủi ro pháp lý.

### Confidence meter — "Độ nét" (cơ chế hòa giải WOW nhanh vs forecast đáng tin)

Bài học V3: onboard nhanh → data mỏng → forecast không thuyết phục ("10 năm không nổi x2") → mất niềm tin. Forced data entry (đề xuất Long) giết funnel. Giải pháp V4:

- Mọi câu trả lời decision + mọi Twin view đi kèm **độ nét** ("ảnh tương lai của anh/chị đang nét ~40%").
- Nhập thêm data (thu nhập, khoản tiết kiệm, mục tiêu) → độ nét tăng **ngay lập tức, nhìn thấy được** → câu trả lời quyết định cụ thể hơn.
- Data completeness từ điều-kiện-tiên-quyết trở thành **chính habit loop**: mỗi decision moment là lý do tự nhiên để làm nét thêm.
- Dưới ngưỡng nét tối thiểu, Bé Tiền trả lời khiêm tốn + nói rõ cần gì để trả lời chắc hơn — không bao giờ tự tin trên data mỏng.

### Giữ từ V3 (vẫn đúng)

- Probability over precision — không bao giờ single-number prediction.
- Weather metaphor (🌧️/⛅/☀️) cho Twin views — comprehension layer đã ship, giữ.
- Predictions-vs-actual calibration — trust through transparency.
- Bé Tiền persona: warm, không phán xét. **Mới:** tone dial cho phép user chỉnh mức thẳng thắn (dịu dàng ↔ nghiêm khắc) — đáp ứng ask "chửi khi tiêu hoang" mà không phá persona floor (§4 kill criterion vẫn hiệu lực).

---

## 💰 Business Model V4

**Nguyên tắc: paywall decisions, không paywall tracking.**

| Tier | Giá | Được gì |
|---|---|---|
| **Free — vĩnh viễn** | 0đ | Toàn bộ tracking (thu chi, tài sản, báo cáo, export), Twin view cơ bản + độ nét, N decision queries/tháng (đủ để nghiện, không đủ cho mốc đời lớn) |
| **Pro** | **68k/tháng** (anchor giữ từ V3 — "2 ly cafe") | Decision queries không giới hạn, shock sim chuyên sâu + liquidation advice, plan-to-goal chi tiết, drift warnings chủ động, scam check |
| ~~CFO 168k~~ | — | **Tier premium tạm gỡ khỏi kế hoạch** — re-validate sau khi có data conversion thật (segment 22-35 chưa chứng minh WTP cho 2 tier) |

- **Vì sao tracking free:** tracking là commodity — thu phí thứ Money Lover/Excel làm được là tự sát với segment này. Free tracking = máy tạo data → độ nét tăng → decision càng giá trị → WTP tăng theo thời gian dùng. Funnel tự nuôi.
- **Affiliate: hoãn ≥ 12 tháng (đến ít nhất 07/2027).** Scam check + liquidation advice chỉ đáng tin khi Bé Tiền không ăn hoa hồng từ bất kỳ sản phẩm tài chính nào. **Neutrality là moat** — các app gắn quỹ/sàn không thể copy. Đây là quyết định chiến lược, không phải "chưa kịp làm".
- **Founding Members (carry-forward, non-negotiable):** 50% lifetime discount khi Pro ra mắt. ~23 slots đã dùng; slots còn lại (tới đủ 50) dành cho cohort segment mới — cùng một lời hứa, không đổi điều khoản.
- Unit economics: cost thực tế $0.0005–$0.0062/user/tháng — margin không phải rủi ro ở quy mô này; rủi ro duy nhất là conversion.

---

## 📣 GTM V4 — Đổi kênh theo segment

- ❌ **Dừng:** community tài chính chuyên nghiệp, giới thiệu qua người làm quỹ/CTCK (kênh này vừa cho ta câu trả lời rõ ràng — đó không phải user, đó là B2B2C contact sau này).
- ✅ **Chuyển sang nơi segment 22-35 thật sự ở:** TikTok tài chính cá nhân, KOL/KOC trẻ, group sinh viên–mới đi làm, build-in-public của founder.
- **Trình tự bắt buộc:** organic + seed nhóm nhỏ (nhóm sinh viên trong feedback là hạt giống có sẵn) → đo D28 cohort mới → chỉ chi tiền/KOL khi D28 ≥ 25%. **Không mua growth trước khi qua gate.**
- Tết 2027 giữ làm marketing moment ("năm mới, quyết định tài chính đầu tiên của năm") — nhưng là **gated bet**: chỉ bùng nổ nếu Gate G2 (dưới) qua.
- Zalo rollout: **đôn lên Phase 5.0-5.2** (amendment 08/07/2026 — OA đã sẵn sàng). Zalo là messaging app phổ thông nhất của segment 22-35 tại VN → mở thêm bề mặt sử dụng organic **trước Tết**. Phân vai kênh giữ nguyên: TikTok là kênh acquisition, Telegram + Zalo là kênh sử dụng. Lưu ý: đây là engineering effort, không phải marketing spend — không vi phạm nguyên tắc "gates trước tiền".

---

## 📋 Roadmap V4 (07/2026 → Tết 2027)

> Nguyên tắc sequencing: (1) ship decision moments trên engine có sẵn trước, (2) sửa activation cho segment mới, (3) mở kênh Zalo (OA sẵn sàng) + hardening + monetization, (4) Tết là gated bet. Zalo đôn lên 5.0-5.2 (amendment 08/07/2026); Encryption dời thành 5.3 — vẫn phải xong trước khi chi tiền growth.

#### Phase 4.5 — Decision Engine Foundation *(~3 tuần, target ship: late July 2026)*
- **Conversational shock sim + liquidation advice** — mở Life Event Simulator (Phase 4B) qua chat tự nhiên; thêm lớp so sánh phương án rút tiền + vẽ lại danh mục (ask của chị Nhung, end-to-end).
- **Plan-to-goal feasibility Q&A** — "X → Y trong Z năm?" trả lời thành thật bằng engine.
- **Độ nét meter v1** — data completeness score + hiển thị trong mọi Twin/decision surface + prompt "làm nét thêm".
- **Quick wins từ feedback:** xuất Excel/Google Sheets (Hà Châu — cũng hợp người chơi chứng khoán/crypto); tone dial persona (dịu dàng ↔ nghiêm khắc).
- Khi ship: **1 đợt re-engagement duy nhất** tới cohort dormant ("Bé Tiền giờ trả lời được câu này…") — sau đó mọi metric đo trên cohort mới.

#### Phase 4.6 — Onboarding Reset cho segment mới *(~2 tuần, August 2026)*
- Onboarding viết lại cho 22-35: goal đầu đời (quỹ khẩn cấp, cưới, mua nhà đầu tiên) thay vì "quản lý tài sản".
- Sửa đường rơi "chưa từng kích hoạt" (nhiều user 0 tin nhắn trong cohort 6/2026) — first message phải tự nổ ra không cần user mở lời.
- Decision moment đầu tiên xảy ra **trong onboarding** (một câu hỏi quyết định thật, trả lời được ngay với data tối thiểu + độ nét thành thật).
- Instrumentation: decision interactions/user/tuần + độ nét trung bình + D28 theo cohort — lên admin dashboard.

#### Phase 4.7 — Guardian Layer *(~2-3 tuần, September 2026)*
- **Drift/overspend warnings** gắn hậu quả Twin (proactive, qua empathy engine có sẵn).
- **Scam check v1** — red-flags library + self-verification guide. Feature flag + kill switch ngay từ ngày đầu. Legal wording review trước ship.

#### Phase 5.0 — Zalo Channel Launch *(~2 tuần, October 2026 — amendment 08/07/2026)*
- Zalo OA **đã sẵn sàng** → không cần spike verification dài; đi thẳng vào webhook + adapter (dựng trên Zalo adapter foundation Phase 4B).
- Validate constraints thực tế: 300-char limit, no-Markdown — content layer phải adapt, không copy nguyên Telegram format.
- Core flows chạy được trên Zalo: capture thu chi, báo cáo, Twin view cơ bản.

#### Phase 5.1 — Zalo Core Product Parity *(~2-3 tuần, October–November 2026)*
- Toàn bộ product hiện tại trên Zalo: intent classifier, asset entry, Twin view, briefing, advisory, **decision queries** (hook chính của V4 phải có mặt trên kênh mới từ đầu).
- Metric Zalo đo chung khung với Telegram: decision interactions/user/tuần + D28 theo cohort, tách theo channel trên admin dashboard.

#### Phase 5.2 — Zalo Mini App *(~2-3 tuần, November–December 2026)*
- Zalo Mini App tương đương Telegram Mini App: Twin dashboard, portfolio view, interactive cone, initData verification trên Zalo SDK.

#### Phase 5.3 — Encryption End-to-End *(~2-3 tuần, December 2026 – January 2027 — dời sau Zalo)*
- Như kế hoạch V3 (at-rest + in-transit hardening, không expose user-facing). Dời sau Zalo 5.0-5.2 (amendment 08/07/2026) vì OA sẵn sàng là cơ hội mở kênh trước Tết; encryption vẫn là nghĩa vụ hạ tầng trước khi scale — **phải xong trước khi chi tiền growth Tết**.

#### Phase 5.7 — Monetization *(~3 tuần, November 2026)*
- License management activate; Free/Pro gate theo **decision queries** (không gate tracking).
- Founding discount honored. Payment VNPay/MoMo/ZaloPay.
- Paywall test = phép đo WTP thật đầu tiên (Gate G3).

#### Tết 2027 — Gated Launch *(December 2026 – February 2027)*
- Tết features (lì xì tracker, year-end review, share images) build ~3 tuần December **chỉ khi Gate G2 qua**.
- Nếu gate không qua: Tết là đợt học tiếp theo với cohort nhỏ, không phải "bùng nổ" — không đốt marketing vào positioning chưa chứng minh.

**Parked / Deferred (không phải kill):** Household mode (segment cũ) · Achievement/Badges 5.4 (sau khi habit thật tồn tại) · Behavioral engine 5.5 (fold dần vào drift warnings) · CFO tier 168k (re-validate bằng data conversion) · B2B2C cobranding (exploratory — chỉ mở khi D28 cohort mới qua gate). *(Zalo đã rút khỏi danh sách này — đôn lên 5.0-5.2 per amendment 08/07/2026.)*

---

## 🎯 Success Metrics V4 + Gates

**North star: weekly decision interactions per active user** (thay "net worth tracked >500tr/user" và "Twin ≥40% daily check" — cả hai đã bị data 6/2026 phủ nhận). Metric phụ bắt buộc đi kèm: **D28 retention cohort mới**.

| Gate | Khi nào | Điều kiện qua | Nếu không qua |
|---|---|---|---|
| **G1 — Decision adoption** | 6 tuần sau Phase 4.5 ship (~mid-Sept) | ≥ 30% active users có ≥ 1 decision interaction/tuần; ≥ 50% users mới thử ≥ 1 decision query trong tuần đầu | Decision Engine không phải hook → dừng 4.7, re-diagnose bằng interview trước khi build tiếp |
| **G2 — Retention segment mới** | Late Oct 2026 (cohort mới n ≥ 20, đủ tuổi D28) | D28 ≥ 25%; độ nét trung bình active users ≥ 60% | Không chi marketing Tết; §1' kích hoạt (dưới) |
| **G3 — WTP** | 4 tuần sau paywall (December) | Free→Pro ≥ 3% trên users chạm paywall | Xem lại giá/gate design trước, segment sau — không vội kết luận segment sai vì 1 biến giá |

### Kill Criteria V4 (kế thừa + recalibrate phase-4.1)

Giữ nguyên: §2 cost (an toàn xa), §3 bug rate, §4 persona violation, §6 Twin calibration. Recalibrate/thêm:

- **§1′ — D28 cohort mới < 20%** (n ≥ 20, sau Phase 4.6): đây là lần trip **thứ hai** của retention line, trên segment + positioning đã sửa → action plan không còn là pivot positioning nữa: interview 5 churned, go/no-go **expense-first hoặc kill sản phẩm** trong 7 ngày. Không có V5 pivot thứ ba cùng công thức.
- **§5′/§7′ — onboarding + positioning** đo trên cohort mới với câu hỏi V4 (option đúng: "app giúp mình quyết định chuyện tiền"), threshold giữ 30%.
- **§8 (MỚI) — Scam-check red line:** 1 case verdict-sai-gây-thiệt-hại được report (user làm theo và mất tiền, hoặc gọi sai một kèo hợp pháp là scam) → **tắt feature bằng kill switch trong 24h**, post-mortem trước khi bật lại. Không threshold, không trung bình — one strike.

---

## 🎨 Guiding Principles V4

1. **Decision-first, dashboard-second** — mọi feature trả lời "user quyết định được gì tốt hơn?"; nếu không có câu trả lời, không build.
2. **Grow with your money** — phục vụ người đang xây tài sản; user lớn thì sản phẩm lớn theo. Không đi tắt tới người giàu.
3. **Honesty là feature** — dám nói "không khả thi", dám show độ nét 40%. Niềm tin xây bằng từng câu trả lời kiểm chứng được, không phải bằng dự báo 10 năm.
4. **Neutrality là moat** — không hoa hồng, không bán sản phẩm tài chính, ≥ 12 tháng. Lời khuyên chỉ đáng tiền khi không ai trả tiền để nó thiên vị.
5. **Đo trên cohort mới, số tuyệt đối cạnh %** — không bao giờ đọc % retention trên n < 20 làm bằng chứng.
6. **Gates trước tiền** — không chi growth/marketing trước khi gate tương ứng qua. Tết là phần thưởng, không phải deadline.
7. **Probability over precision** *(giữ V3)* — cones là backend; câu trả lời user thấy là khuyến nghị + độ tin cậy.
8. **Ship fast, iterate** *(giữ V3)* — engine có sẵn, V4 chủ yếu là bề mặt + framing; tốc độ vẫn là lợi thế.
9. **Persona floor bất khả xâm phạm** *(giữ V3)* — tone dial chỉnh độ thẳng thắn, không bao giờ chỉnh được sự tôn trọng.

---

## 📝 Strategic Decisions Log (V4 Session — 05/07/2026)

1. **Cắt hẳn Mass Affluent** khỏi target trực tiếp — approved by founder.
2. **Twin reframe: Future Vision → Decision Engine** — approved by founder.
3. Target mới: 22-35 tuổi, Level 0→1 (0 – 500tr), "thế hệ đang xây".
4. 4 decision moments: shock sim + liquidation, plan-to-goal, drift warning, scam check (red-flags only).
5. Độ nét (confidence meter) thay forced data entry — data completeness = habit mechanic.
6. Paywall decisions, free tracking vĩnh viễn; anchor 68k giữ; CFO tier 168k tạm gỡ.
7. Affiliate hoãn ≥ 12 tháng (neutrality moat).
8. GTM → TikTok/KOL trẻ/sinh viên; dừng kênh community tài chính chuyên nghiệp; Zalo re-evaluate post-Tết.
9. North star → weekly decision interactions + D28 cohort mới; bỏ "net worth >500tr/user".
10. Roadmap: 4.5 Decision Engine → 4.6 Onboarding Reset → 4.7 Guardian → 5.0 Encryption (lùi) → 5.7 Monetization → Tết gated. Household/Zalo/Badges/Behavioral parked.
11. Founding 50 commitment giữ nguyên; ~27 slots còn lại dành cho cohort segment mới.
12. Kill criteria recalibrate: §1′ (lần trip thứ 2 = expense-first hoặc kill, không pivot thứ 3), thêm §8 scam-check one-strike.

### Amendment — 08/07/2026 (founder decision)

13. **Zalo đôn lên Phase 5.0-5.2** (October–December 2026), thay vì deferred post-Tết — OA đã sẵn sàng; Zalo là messaging app phổ thông nhất của segment 22-35 tại VN, mở bề mặt sử dụng organic trước Tết. *Sửa một phần decision #8 và #10 ở trên (phần Zalo).*
14. **Encryption End-to-End dời thành Phase 5.3** (December 2026 – January 2027) — sau Zalo, nhưng vẫn giữ ràng buộc gốc: phải xong **trước** khi chi tiền growth Tết.

---

## 📝 Changelog

**V4 (current):** Post-soft-launch pivot (07/2026)
- Segment: cắt Mass Affluent → 22-35 builders (Level 0→1)
- Twin: Future Vision → Decision Engine (4 decision moments trên engine sẵn có)
- Độ nét meter, paywall decisions, affiliate deferred, GTM young channels, gates + kill criteria mới
- Pivot rationale: [MIGRATION_NOTES_V3_TO_V4.md](../archive/MIGRATION_NOTES_V3_TO_V4.md)
- *Amendment 08/07/2026:* Zalo đôn lên 5.0-5.2 (OA sẵn sàng), Encryption dời thành 5.3 (vẫn trước growth spend Tết)

**V3:** [archived](../archive/strategy-v3.md) — Financial Twin differentiator, pricing 68/168 volume play, Tết 2027 roadmap. Superseded vì soft-launch data phủ nhận segment + passive-prediction hook.

**V2:** [archived](../archive/strategy-v2.md) — Pivot to Personal CFO positioning (wealth-first instead of expense-first)

**V1:** [archived](../archive/strategy-v1.md) — Original "Finance Assistant" strategy (expense tracking focus)

> **Note for future-Phuong:** Khi tạo V5, follow same pattern: archive current strategy.md → strategy-v4.md, create MIGRATION_NOTES_V4_TO_V5.md, never delete. Và nhớ §1′: nếu retention line trip lần nữa trên cohort mới, câu trả lời không phải là một bản strategy V5 đẹp hơn.

---

**Từ đây, mỗi quyết định optimize cho một thứ: người trẻ Việt ra quyết định tiền bạc tốt hơn — và quay lại tuần sau để ra quyết định tiếp theo. 🧭💚**
