# Phase 4B — Financial Twin Polish + Life Events + Cashflow v2

**Duration:** ~4 tuần (18–22 dev days)  
**Status:** Current  
**Branch:** `claude/phase-4b-docs-PFcty`  
**Mục tiêu:** Biến Financial Twin từ "xem tương lai trừu tượng" thành "lập kế hoạch cuộc đời cụ thể" — tích hợp các mốc đời thực của người Việt (mua nhà, kết hôn, con cái), cảnh báo cashflow thông minh, và mở rộng kênh Zalo.

---

## Design Philosophy

### 1. "Life is the Lens" — Cuộc đời là lăng kính
Monte Carlo cones trở nên có ý nghĩa khi người dùng thấy sự kiện đời thực của mình trong đó. Thay vì "tài sản ròng 2035 là X tỷ", câu hỏi trở thành: "Nếu mua nhà năm 2028, mình vẫn có đủ tiền không?"

### 2. "Cash is King, Surprise is the Enemy" — Tiền mặt mới quyết định, bất ngờ mới nguy hiểm
Cashflow Forecasting v2 tập trung vào **phát hiện sớm**: tự động nhận diện thu chi định kỳ và cảnh báo khi tháng tới có nguy cơ thiếu tiền — trước khi người dùng nhận ra.

### 3. "Progressive Trust" — Tin tưởng dần dần
Không ép người dùng nhập thông tin ngay. Life events và recurring patterns đều có flow **xác nhận**: hệ thống đề xuất, người dùng duyệt. Không bao giờ dùng dữ liệu chưa được xác nhận trong dự báo.

### 4. "One Channel at a Time" — Một kênh mỗi lúc
Zalo adapter được xây dựng với cashflow alert làm feature đầu tiên. Không cố port toàn bộ app lên Zalo ngay — prove the channel, then expand.

---

## Epic Overview

| Epic | Tên | Ngày ước tính | Stories |
|---|---|---|---|
| Epic 1 | Twin Polish | 4 ngày | S1–S5 |
| Epic 2 | Life Event Simulator | 7 ngày | S6–S13 |
| Epic 3 | Cashflow Forecasting v2 | 7 ngày | S14–S20 |
| Epic 4 | Zalo Adapter Foundation | 4 ngày | S21–S24 |
| **Tổng** | | **~22 ngày** | **24 stories** |

---

## Epic 1 — Twin Polish (4 ngày)

### Mục tiêu
Cải thiện chất lượng Financial Twin từ Phase 4A dựa trên các khoảng trống thực tế: accuracy tracking, narrative cá nhân hóa hơn, UX so sánh rõ ràng hơn, và insight về nguồn gốc bất định.

---

### S1: Historical Accuracy Tracking

**Mô tả:** Mỗi tuần khi cron chạy lại MC, lưu `actual_net_worth` thực tế tại thời điểm đó so với P50 đã dự báo tuần trước. Hiển thị trong morning briefing: "Tuần trước Bé Tiền dự báo P50 = 1.2 tỷ, thực tế = 1.18 tỷ (−2%)."

**DB change:**
```sql
ALTER TABLE twin_projections ADD COLUMN actual_net_worth NUMERIC(20,2);
```

**Logic:**
- Weekly cron Sunday 23:00: trước khi ghi projection mới, tìm projection của tuần trước cho cùng user_id → điền `actual_net_worth` từ current net worth snapshot
- `accuracy_delta_pct = (actual - p50_at_forecast) / p50_at_forecast * 100`

**Morning briefing format:**
```
📊 Độ chính xác dự báo: tuần trước P50 = 1.2 tỷ → thực tế 1.18 tỷ (−2%)
```

**Acceptance criteria:**
- Migration runs without breaking existing rows
- Cron điền `actual_net_worth` trước khi tạo projection mới
- Morning briefing hiển thị delta khi có ≥ 2 weekly projections
- Nếu actual < P10 → tone reassure; nếu actual > P90 → celebrate; trường hợp bình thường → neutral

---

### S2: On-Demand Recompute Trigger

**Mô tả:** Khi user thêm/cập nhật tài sản có giá trị thay đổi ≥ 5% net worth → enqueue background twin recompute (debounce 30 phút).

**Implementation:**
```python
# asset_service.py — sau khi update/create asset
change_pct = abs(delta_net_worth) / current_net_worth
if change_pct >= Decimal("0.05"):
    await event_bus.publish(AssetSignificantChangeEvent(user_id=user_id))

# twin_recompute_consumer.py
@debounce(seconds=1800)  # 30 minutes
async def handle_asset_significant_change(event: AssetSignificantChangeEvent):
    await twin_recompute_task.enqueue(user_id=event.user_id)
```

**Notification khi xong:**
```
🔮 Bé Tiền đã cập nhật dự báo tương lai của bạn dựa trên thay đổi tài sản vừa rồi.
```

**Acceptance criteria:**
- Asset change ≥ 5% net worth → recompute within 30 minutes
- Asset change < 5% → không trigger (chờ Sunday cron)
- 3 asset changes trong 5 phút → chỉ 1 recompute (debounce)
- Notification gửi SAU khi recompute xong
- `asset_service` chỉ publish event, không recompute trực tiếp (layer contract)

---

### S3: LLM Narrative v2

**Mô tả:** Cải thiện LLM prompt cho twin narrative: thêm context giàu hơn về wealth level, thay đổi tài sản gần nhất, và life events.

**Prompt additions:**
```python
context = {
    "wealth_level": user.wealth_level,              # e.g. "Tích lũy"
    "top_asset_changes_30d": [                       # top 2 assets by % change
        {"name": "VNINDEX", "change_pct": +12.3},
        {"name": "BĐS Hà Nội", "change_pct": -2.1},
    ],
    "has_life_events": len(active_life_events) > 0,
    "life_event_summary": "Mua nhà 2028, Con đầu lòng 2030",
}
```

**Anti-patterns để loại bỏ:**
- ❌ "Tương lai tài chính của bạn trông tích cực"
- ❌ "Bạn đang đi đúng hướng"
- ✅ "Với danh mục ở mức Tích lũy, VNINDEX tăng 12% vừa rồi đang kéo P50 của bạn lên đáng kể"

**Acceptance criteria:**
- Narrative đề cập đúng wealth level
- Nếu user có life events → nhắc ≥ 1 event cụ thể
- Không có generic phrases (kiểm tra bằng `prompt-tester` agent)
- Prompt tester passes persona check

---

### S4: Scenario Comparison UX Enhancement

**Mô tả:** Mini App: thêm delta badges và CTA rõ ràng để user thấy giá trị của việc tối ưu hóa savings.

**UI changes:**
- Delta badge tại mỗi milestone (2027, 2030, 2035): "Optimal +23%"
- CTA: "Cần thêm **X triệu/tháng** để đạt Optimal"  
  *(X = (optimal_p50 - current_p50) / months_to_horizon / savings_multiplier)*
- Tooltip: "Optimal giả định bạn tăng tiết kiệm thêm 10% mỗi tháng"

**Acceptance criteria:**
- Delta badges hiển thị tại 3 milestone years
- CTA hiển thị số tiền cụ thể (rounded to nearest 500k)
- Tooltip giải thích Optimal assumption
- Mobile responsive (tested on 375px width)

---

### S5: Twin Cone Uncertainty Breakdown

**Mô tả:** Hiển thị top 2 asset classes đóng góp nhiều nhất vào sự bất định của cone — giúp user hiểu tại sao cone rộng hay hẹp.

**Backend computation:**
```python
def compute_uncertainty_breakdown(allocation: Dict[AssetClass, float],
                                   distributions: Dict[AssetClass, Distribution]
                                   ) -> List[UncertaintyContributor]:
    contributions = []
    for asset_class, weight in allocation.items():
        vol = distributions[asset_class].annual_volatility
        contribution = weight * vol  # weighted volatility contribution
        contributions.append(UncertaintyContributor(asset_class, contribution))
    total = sum(c.contribution for c in contributions)
    return sorted(
        [UncertaintyContributor(c.asset_class, c.contribution / total) 
         for c in contributions],
        key=lambda x: x.contribution, reverse=True
    )[:2]
```

**Display format:**
```
Yếu tố bất định lớn nhất:
• Cổ phiếu VN: 42% đóng góp vào độ rộng cone
• Tiền điện tử: 31% đóng góp vào độ rộng cone
```

**Acceptance criteria:**
- Top 2 asset classes with contribution %
- Contributions sum ≈ 100% (full breakdown available via expand)
- Tooltip: "asset càng volatile → cone càng rộng"

---

## Epic 2 — Life Event Simulator (7 ngày)

### Mục tiêu
Cho phép user thêm các mốc đời thực → xem impact lên Financial Twin. Feature tạo "cá nhân hóa sâu" nhất trong Phase 4B.

**Critical path:** S6 → S7 → S8 → (S9 ‖ S11) → S10 → S12 → S13

---

### S6: Life Event Data Model + Migration

**DB migration:**
```sql
CREATE TABLE life_events (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                   UUID NOT NULL REFERENCES users(id),
    event_type                VARCHAR(50) NOT NULL,
    title                     VARCHAR(200),
    planned_date              DATE,
    one_time_cost             NUMERIC(20,2),
    recurring_monthly_delta   NUMERIC(20,2),
    recurring_duration_months INTEGER,
    notes                     TEXT,
    is_active                 BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at                TIMESTAMPTZ,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX life_events_user_active_idx ON life_events(user_id)
    WHERE deleted_at IS NULL AND is_active = TRUE;
```

**Python enum:**
```python
class LifeEventType(str, Enum):
    BUY_HOUSE         = "buy_house"
    WEDDING           = "wedding"
    FIRST_CHILD       = "first_child"
    CHILD_UNIVERSITY  = "child_university"
    EARLY_RETIREMENT  = "early_retirement"
    CUSTOM            = "custom"
```

**Pydantic models:** `LifeEventCreate`, `LifeEventRead`, `LifeEventUpdate`, `LifeEventImpact`

**Service:** `life_event_service.py` — CRUD + soft delete. Không `db.commit()` (layer contract).

---

### S7: Vietnamese Life Event Presets

**Mô tả:** Preset defaults phù hợp thị trường VN, dựa trên dữ liệu thực tế 2025-2026.

**`life_events/presets.py`:**

| event_type | one_time_cost | recurring_monthly_delta | recurring_duration_months | Ghi chú |
|---|---|---|---|---|
| buy_house | 3,500,000,000 | −8,000,000 | 240 | Căn hộ 3.5 tỷ, vay 70% lãi 8.5%/năm 20 năm |
| wedding | 500,000,000 | 0 | 0 | Chi phí đám cưới trung bình HCM/HN 2026 |
| first_child | 0 | −8,000,000 | 216 | Nuôi con từ 0–18 tuổi, không kể học phí CĐ/ĐH |
| child_university | 500,000,000 | −5,000,000 | 48 | 4 năm ĐH + sinh hoạt phí, trường công lập |
| early_retirement | 0 | −25,000,000 | 0 | Thu nhập = 0, chi phí sinh hoạt cơ bản |

*Source: CBRE VN Housing Report 2026, VCCI salary survey, Bộ GD&ĐT học phí 2026.*

Tất cả copy giải thích preset → `content/vi.yaml` (không hardcode trong code).

**Acceptance criteria:**
- 5 preset types với defaults như trên
- User có thể override bất kỳ field nào
- Preset copy trong `content/vi.yaml`

---

### S8: Monte Carlo Integration — Life Events

**Mô tả:** Extend Monte Carlo engine để inject life event cashflows vào các simulation paths.

**`twin/engine/life_events.py`:**
```python
def apply_life_events(
    paths: np.ndarray,           # shape: (n_paths, n_months)
    life_events: List[LifeEvent],
    time_grid: List[date],
) -> np.ndarray:
    """Apply life event cashflows to all MC paths. Modifies paths in-place."""
    for event in life_events:
        if event.planned_date is None:
            continue
        try:
            event_idx = next(
                i for i, d in enumerate(time_grid)
                if d >= event.planned_date
            )
        except StopIteration:
            continue  # event beyond horizon — skip

        if event.one_time_cost:
            paths[:, event_idx:] -= float(event.one_time_cost)

        if event.recurring_monthly_delta and event.recurring_duration_months:
            end_idx = min(event_idx + event.recurring_duration_months, len(time_grid))
            for month_offset in range(end_idx - event_idx):
                paths[:, event_idx + month_offset] += (
                    float(event.recurring_monthly_delta) * (month_offset + 1)
                )

    np.maximum(paths, 0, out=paths)  # floor at 0 (net worth cannot go negative in model)
    return paths
```

**Integration:** Gọi `apply_life_events()` sau khi generate paths, trước khi aggregate cones.

**Performance target:** 5 events × 1000 paths × 240 months < 500ms (NumPy vectorized).

**Acceptance criteria:**
- buy_house event: P50 tại planned_date giảm đúng one_time_cost
- Recurring delta tích lũy đúng theo tháng
- Multiple events không double-count
- Benchmark < 500ms
- Không có NaN hoặc negative values trong output

---

### S9: Telegram Interface — Life Events

**Mô tả:** `/life_events` command với full add/view/delete flow qua Telegram conversation.

**Command menu:**
```
/life_events
→ [📋 Xem danh sách | ➕ Thêm mới | 🗑 Xóa]
```

**Add flow (ConversationHandler):**
```
STATE_SELECT_TYPE:
  Bot: "Bạn đang lên kế hoạch cho sự kiện nào?"
  Buttons: [🏠 Mua nhà | 💒 Kết hôn | 👶 Con đầu lòng | 🎓 Học phí ĐH | 🌴 Nghỉ hưu sớm | ✏️ Tùy chỉnh]

STATE_REVIEW_PRESET (chọn Mua nhà):
  Bot: "Bé Tiền sẽ dùng ước tính:
        • Chi phí một lần: 3.5 tỷ
        • Trả góp hàng tháng: -8 triệu/tháng trong 20 năm
        • Năm dự kiến: bạn muốn mua năm nào?"
  → User nhập năm (e.g. "2028")
  Buttons: [✅ Dùng ước tính này | ✏️ Tùy chỉnh chi tiết]

STATE_CONFIRM:
  Bot: "Tóm tắt kế hoạch mua nhà của bạn: ..."
  Buttons: [✅ Xác nhận | ✏️ Sửa lại | ❌ Hủy]

→ Save → trigger twin recompute (S2) → send impact chart (S10)
```

**Acceptance criteria:**
- Full add flow hoạt động end-to-end
- Xem danh sách: tất cả active events với date + cost summary
- Xóa: confirm trước khi soft delete
- `planned_date < today` → friendly error
- Sau khi save: "🔮 Bé Tiền đang tính lại tương lai của bạn..."

---

### S10: Life Event Impact Visualization

**Mô tả:** "Before/After" PNG chart: 2 cones chồng nhau — Current (không có event) vs With Event.

**Chart spec:**
- Before cone: màu xanh lam nhạt (rgba(66, 133, 244, 0.3))
- With event cone: màu cam nhạt (rgba(255, 152, 0, 0.3))
- P50 lines: solid, cùng màu tương ứng
- Impact labels tại milestone years: "−1.2 tỷ vào 2035"
- Watermark: "dự phóng, không phải dự đoán"

**Gửi tự động sau khi user confirm thêm event mới.**

**Acceptance criteria:**
- 2 cones phân biệt màu sắc rõ ràng
- Impact labels tại 2027, 2030, 2035
- Watermark hiển thị
- PNG render < 500ms
- Mobile readable (1000×600px)

---

### S11: Mini App Life Events Panel

**Mô tả:** Tab "Kế hoạch" trong Mini App với timeline events và toggle xem impact.

**API endpoint:**
```
GET /api/life-events              → list user's life events
GET /api/twin/projection?exclude_event_ids=uuid1,uuid2  → projection without specific events
```

**UI:**
- Horizontal timeline: events ordered by planned_date, grouped by year
- Each event: icon + title + cost estimate
- Toggle switch: ON/OFF → call API → re-render cone chart
- "Thêm sự kiện" → `tg://resolve?domain=BeThienBot&start=life_events` deep link

**Acceptance criteria:**
- Tab load < 1s
- Toggle → cone re-render < 500ms (use cached base projection)
- Timeline shows planned year + estimated total cost
- Deep link hoạt động trên mobile Telegram

---

### S12: LLM Narrative for Life Events

**Mô tả:** Khi user xem impact của life event, Bé Tiền generate 3-4 câu narrative ấm áp về ý nghĩa và gợi ý thực tế.

**Prompt additions per event_type:**

| event_type | Key message | Suggested action |
|---|---|---|
| buy_house | "Nhà là tài sản, khoản vay là đòn bẩy — đây là trade-off bình thường" | "Tăng tiết kiệm X triệu/tháng để bù đắp impact" |
| wedding | "Chi phí ban đầu, nhưng 2 người cùng kế hoạch hiệu quả hơn" | "Lập quỹ chung với bạn đời" |
| first_child | "Trách nhiệm lớn nhưng hoàn toàn có thể plan được" | "Bắt đầu quỹ trẻ em ngay hôm nay" |
| child_university | "Đầu tư cho con là khoản sinh lời cao nhất" | "Gửi tiết kiệm có kỳ hạn từ bây giờ" |
| early_retirement | "Nghỉ hưu sớm đòi hỏi tài sản đủ lớn để generate passive income" | "Mục tiêu X tỷ để cover Y triệu/tháng indefinitely" |

**Tone rules:**
- KHÔNG BAO GIỜ gợi ý trì hoãn kết hôn hoặc không sinh con vì lý do tài chính
- KHÔNG dùng: "cảnh báo", "nguy hiểm", "thất bại tài chính", "rủi ro cao"
- DÙNG: "trade-off bình thường", "có thể lên kế hoạch được", "đây là lúc tốt để..."

**Acceptance criteria:**
- Narrative reference impact amount cụ thể
- Tone test (prompt-tester agent) passes persona check
- Gợi ý hành động cụ thể liên quan event type

---

### S13: Life Events Tests + Benchmarks

**Coverage:**
```
tests/twin/test_life_events_engine.py:
  - test_buy_house_reduces_p50_at_event_date
  - test_recurring_delta_accumulates_monthly
  - test_multiple_events_no_double_count
  - test_event_beyond_horizon_skipped
  - test_paths_floored_at_zero

tests/life_events/test_service.py:
  - test_create_life_event_with_preset
  - test_soft_delete
  - test_list_active_only

tests/integration/test_life_events_flow.py:
  - test_telegram_add_flow_end_to_end
  - test_add_triggers_twin_recompute

benchmarks/bench_life_events.py:
  - bench_5_events_1000_paths_240_months → target < 500ms
```

**Acceptance criteria:**
- All unit tests pass
- Integration test covers happy path
- Benchmark result documented in `phase-4B-benchmark.md`

---

## Epic 3 — Cashflow Forecasting v2 (7 ngày)

### Mục tiêu
Tự động phát hiện thu chi định kỳ, dự báo 3 tháng tới, cảnh báo sớm khi có nguy cơ thiếu tiền.

**Critical path:** S14 → S15 → S16 → S17 → (S18 ‖ S19 ‖ S20 in parallel)

---

### S14: Recurring Transaction Detector

**Mô tả:** Phân tích lịch sử giao dịch để nhận diện patterns định kỳ bằng rule-based algorithm (không cần ML model).

**`cashflow/detector.py` — core algorithm:**
```python
def detect_recurring_patterns(
    transactions: List[Transaction],
    lookback_months: int = 3,
    min_occurrences: int = 3,
    confidence_threshold: float = 0.70,
) -> List[RecurringCandidate]:
    # Group by (category_id, amount_band_50k, day_of_month_band_3days)
    # amount_band_50k: round(amount / 50000) * 50000
    # day_of_month_band: bucket into [1-4, 5-7, 8-11, 12-15, 16-19, 20-23, 24-27, 28-31]
    groups = defaultdict(list)
    for tx in filter_last_n_months(transactions, lookback_months):
        key = (tx.category_id, amount_band(tx.amount), day_band(tx.date.day))
        groups[key].append(tx)

    candidates = []
    for key, txs in groups.items():
        unique_months = {(tx.date.year, tx.date.month) for tx in txs}
        confidence = len(unique_months) / lookback_months
        if confidence >= confidence_threshold:
            candidates.append(RecurringCandidate(
                category_id=key[0],
                amount=median_amount(txs),
                typical_day_of_month=modal_day(txs),
                frequency="monthly",
                confidence=confidence,
                pattern_type="income" if median_amount(txs) > 0 else "expense",
            ))
    return candidates
```

**DB: Bảng `recurring_patterns`:**
```sql
CREATE TABLE recurring_patterns (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES users(id),
    pattern_type         VARCHAR(20) NOT NULL,     -- 'income' | 'expense'
    description          VARCHAR(200),
    amount               NUMERIC(20,2) NOT NULL,
    frequency            VARCHAR(20) NOT NULL DEFAULT 'monthly',
    typical_day_of_month INTEGER,
    category_id          UUID REFERENCES categories(id),
    confidence           NUMERIC(5,4) NOT NULL,
    is_confirmed         BOOLEAN NOT NULL DEFAULT FALSE,
    dismissed_until      TIMESTAMPTZ,
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    first_seen_at        TIMESTAMPTZ,
    last_seen_at         TIMESTAMPTZ,
    deleted_at           TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX recurring_patterns_user_confirmed_idx
    ON recurring_patterns(user_id)
    WHERE deleted_at IS NULL AND is_confirmed = TRUE;
```

**Cron:** Chạy Monday 06:00 AM hàng tuần.

**Acceptance criteria:**
- Salary (ngày 1, ~20tr mỗi tháng, 3 tháng liên tiếp) detected với confidence ≥ 0.9
- Tiền nhà (ngày 5, fixed amount) detected với confidence ≥ 0.85
- Random transactions KHÔNG detected (confidence < 0.7)
- Chỉ xử lý user có ≥ 3 tháng transaction history
- Performance: < 2s cho 500 transactions

---

### S15: User Review Flow for Detected Patterns

**Mô tả:** Telegram flow để user confirm hoặc dismiss các patterns mới được detect.

**Trigger:** Cron sau detection — nếu có unconfirmed patterns chưa bị dismiss:

**Message format:**
```
💡 Bé Tiền nhận ra 3 khoản thu chi định kỳ của bạn:

1. Lương (~20 triệu, ngày 1 hàng tháng)
2. Tiền nhà (−8 triệu, ngày 5 hàng tháng)
3. Phí gym (−500k, ngày 15 hàng tháng)

Xác nhận để Bé Tiền dùng vào dự báo cashflow nhé?
```

**Inline buttons per pattern:** `[✅ Đúng | ❌ Không phải | ✏️ Sửa]`

**Acceptance criteria:**
- Hiển thị tối đa 5 patterns per message (tránh overwhelm)
- ✅ → `is_confirmed = true` → dùng trong forecast
- ❌ → `dismissed_until = now() + 30 days` (không hiện lại 30 ngày)
- ✏️ Sửa → ask for corrected amount, then confirm
- Không send duplicate message cho cùng pattern

---

### S16: 3-Month Cashflow Forecast Model

**`cashflow/forecast.py`:**
```python
async def compute_cashflow_forecast(
    user_id: UUID,
    current_balance: Decimal,
    confirmed_patterns: List[RecurringPattern],
    current_month_actuals: Dict[str, Decimal],  # actual income/expense so far this month
    horizon_months: int = 3,
) -> CashflowForecast:
    monthly_data = []
    running_balance = current_balance

    for month_offset in range(horizon_months):
        target_month = date.today().replace(day=1) + relativedelta(months=month_offset)
        
        projected_income = sum_income_patterns(confirmed_patterns, target_month)
        projected_expense = sum_expense_patterns(confirmed_patterns, target_month)
        
        if month_offset == 0:
            # Adjust for actuals already occurred this month
            projected_income = max(0, projected_income - current_month_actuals.get("income", 0))
            projected_expense = max(0, projected_expense - current_month_actuals.get("expense", 0))
        
        net = projected_income - projected_expense
        running_balance += net
        monthly_data.append(MonthlyForecast(
            month=target_month,
            income=projected_income,
            expense=projected_expense,
            net=net,
            balance_eom=running_balance,
        ))

    low_balance_threshold = user_settings.cashflow_alert_threshold or default_threshold(confirmed_patterns)
    low_balance_months = [m for m in monthly_data if m.balance_eom < low_balance_threshold]
    
    return CashflowForecast(
        user_id=user_id,
        forecast_date=date.today(),
        horizon_months=horizon_months,
        monthly_data=monthly_data,
        low_balance_risk=bool(low_balance_months),
        low_balance_month=min(low_balance_months, key=lambda m: m.month).month if low_balance_months else None,
        low_balance_threshold=low_balance_threshold,
    )
```

**DB: Bảng `cashflow_forecasts`:**
```sql
CREATE TABLE cashflow_forecasts (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID NOT NULL REFERENCES users(id),
    forecast_date         DATE NOT NULL,
    computed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    horizon_months        INTEGER NOT NULL DEFAULT 3,
    monthly_data          JSONB NOT NULL,
    low_balance_risk      BOOLEAN NOT NULL DEFAULT FALSE,
    low_balance_month     DATE,
    low_balance_threshold NUMERIC(20,2),
    engine_version        VARCHAR(20) NOT NULL DEFAULT '1.0',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX cashflow_forecasts_user_date_idx
    ON cashflow_forecasts(user_id, forecast_date DESC);
```

**Cron:** Daily 01:00 AM recompute.

**Acceptance criteria:**
- Chỉ dùng `is_confirmed = true` patterns
- Actuals tháng hiện tại giảm projected amount cho tháng đó
- `balance_eom` tích lũy đúng từ current_balance
- p95 compute < 200ms
- Engine version stored for debugging

---

### S17: Low-Balance Alert Engine

**`cashflow/alert.py`:**
```python
async def check_and_send_cashflow_alerts(user_id: UUID, forecast: CashflowForecast):
    if not forecast.low_balance_risk:
        return

    alert_key = f"cashflow_alert:{user_id}:{forecast.low_balance_month.isoformat()}"
    if await redis.exists(alert_key):
        return  # already sent for this month

    message = format_cashflow_alert(forecast)
    notifiers = await get_notifiers(user_id)
    for notifier in notifiers:
        await notifier.send(message)

    await redis.setex(alert_key, 7 * 24 * 3600, "sent")  # dedup for 7 days
```

**Alert message template** (`content/vi.yaml`):
```yaml
cashflow_alert:
  title: "⚠️ Cashflow tháng {month}"
  body: >
    Bé Tiền dự báo số dư tháng {month} có thể xuống còn ~{balance} —
    dưới mức an toàn {threshold} của bạn.

    Nguyên nhân chính: {top_expense_pattern}
    Gợi ý: {suggested_action}
  footer: "📊 Xem chi tiết → {mini_app_link}"
```

**Threshold default:** `avg(monthly_expense from confirmed_patterns) × 1.0` (1 tháng chi tiêu)

**Acceptance criteria:**
- Alert trigger khi bất kỳ tháng nào trong horizon có `balance_eom < threshold`
- Không lặp lại cho cùng `low_balance_month` trong 7 ngày (Redis dedup)
- Alert gửi lại nếu forecast cập nhật, balance xấu hơn sau khi đã recover
- Tone: "có thể", "dự báo" — không alarming
- User customize threshold qua `/settings cashflow_threshold 15000000`

---

### S18: Cashflow Waterfall Chart

**`cashflow/chart.py`:**

**Spec:**
- Size: 1000×600px
- Grouped bars: income (xanh #4CAF50) + expense (đỏ #F44336) per month
- Line overlay: balance EOM (tím #7C4DFF)
- X-axis labels: "Tháng 8/2026", "Tháng 9/2026", "Tháng 10/2026"
- Y-axis: VND formatted as "tr" (triệu)
- Net badge trên mỗi tháng: "+5.2 tr" (xanh) hoặc "−2.1 tr" (đỏ)
- Watermark: "dự báo dựa trên thu chi định kỳ"

**Acceptance criteria:**
- Render p95 < 500ms
- Labels Vietnamese
- Income/expense bars clearly distinguishable
- Balance line visible
- PNG output suitable for Telegram

---

### S19: Morning Briefing Cashflow Summary

**Format** (thêm vào sau wealth section, chỉ khi `len(confirmed_patterns) >= 2`):
```
💰 Cashflow tháng tới: dự kiến +5.2 triệu (thu 20.5tr − chi 15.3tr)
⚠️ Tháng 9: số dư có thể xuống ~12 triệu — dưới ngưỡng an toàn bạn đặt
```

**Điều kiện hiển thị:**
- `len(confirmed_patterns) >= 2` — tránh false confidence khi data ít
- `forecast.horizon_months >= 1`
- Nếu `low_balance_risk = True` → thêm dòng ⚠️

**Acceptance criteria:**
- Không hiển thị nếu < 2 confirmed patterns
- Net amount (không chỉ income/expense riêng lẻ)
- Không regression morning briefing format hiện tại

---

### S20: Cashflow Tab in Mini App

**API:**
```
GET /api/cashflow/forecast     → CashflowForecast (current)
GET /api/cashflow/patterns     → List[RecurringPattern] (confirmed)
POST /api/cashflow/patterns    → add manual pattern
PATCH /api/cashflow/patterns/{id}  → update amount/day
```

**UI:**
- Tab "Dòng tiền" (thêm vào Mini App navigation)
- Waterfall chart at top (pre-rendered PNG hoặc Chart.js)
- "Thu định kỳ" list + "Chi định kỳ" list
- Editable: tap pattern → edit amount/day
- Alert banner (nếu `low_balance_risk`) → links to explanation dialog
- "Thêm thủ công" FAB button

**Acceptance criteria:**
- Tab load < 1s
- Patterns editable từ Mini App
- Alert banner hiển thị và có CTA
- Responsive mobile

---

## Epic 4 — Zalo Adapter Foundation (4 ngày)

### Mục tiêu
Prove Zalo channel hoạt động bằng cashflow alert đầu tiên. Channel-agnostic `Notifier` port đã có từ Phase 4A — chỉ cần implement `ZaloNotifier`.

**Prerequisite (operator task):** Zalo Official Account đã được approved và có `access_token`.

### Architecture
```
CashflowAlertService
  → get_notifiers(user_id)           # returns [TelegramNotifier] or [TelegramNotifier, ZaloNotifier]
     ZaloNotifier (implements Notifier port)
       → ZaloOAClient.send_message(zalo_user_id, content)
```

---

### S21: Zalo Official Account Setup + SDK

**`adapters/zalo_oa.py`:**
```python
class ZaloOAClient:
    BASE_URL = "https://openapi.zalo.me/v3.0/oa"

    def __init__(self, access_token: str):
        self._access_token = access_token
        self._session: aiohttp.ClientSession | None = None

    async def send_message(self, recipient_id: str, text: str) -> bool:
        payload = {
            "recipient": {"user_id": recipient_id},
            "message": {"text": text},
        }
        return await self._post("/message/cs", payload)

    async def send_image_message(self, recipient_id: str, image_url: str,
                                  caption: str) -> bool:
        ...

    async def _post(self, path: str, payload: dict) -> bool:
        # Retry on 429: exponential backoff 2s, 4s, 8s (3 retries)
        # Other errors: log + return False (fail-open)
        ...
```

**Env vars (không hardcode):**
```
ZALO_OA_ACCESS_TOKEN=...
ZALO_OA_SECRET_KEY=...
ZALO_APP_ID=...
```

**Acceptance criteria:**
- Client có thể gửi test message thành công
- 429 retry: exponential backoff 2s/4s/8s, max 3 retries
- Non-retry errors: log + return False (không raise)
- Unit tests dùng mocked aiohttp session

---

### S22: ZaloNotifier implementing Notifier Port

**`adapters/zalo_notifier.py`:**
```python
from ports.notifier import Notifier, Message

class ZaloNotifier(Notifier):
    channel = "zalo"

    def __init__(self, client: ZaloOAClient, zalo_user_id: str):
        self._client = client
        self._zalo_user_id = zalo_user_id

    async def send(self, message: Message) -> bool:
        plain_text = strip_markdown(message.text)  # Zalo không hỗ trợ Markdown
        plain_text = plain_text[:300]               # Zalo message limit
        return await self._client.send_message(self._zalo_user_id, plain_text)

    async def send_image(self, image_bytes: bytes, caption: str) -> bool:
        image_url = await self._client.upload_image(image_bytes)
        return await self._client.send_image_message(
            self._zalo_user_id, image_url, caption[:100]
        )
```

**Acceptance criteria:**
- Passes `ports/notifier_test_suite.py` (shared với TelegramNotifier)
- Markdown bị strip trước khi gửi
- Message bị truncate tại 300 chars
- Trả về `False` khi fail, không raise exception

---

### S23: User Zalo Linking Flow

**DB changes:**
```sql
ALTER TABLE users ADD COLUMN zalo_user_id VARCHAR(50);
ALTER TABLE users ADD COLUMN cashflow_alert_threshold NUMERIC(20,2);

CREATE TABLE zalo_link_tokens (
    token       VARCHAR(10) PRIMARY KEY,      -- "BT-XXXXXX" format
    user_id     UUID NOT NULL REFERENCES users(id),
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Telegram flow:**
```
/link_zalo
→ Bot: "Để nhận thông báo qua Zalo:
  1️⃣ Mở Zalo → tìm 'Bé Tiền' → Follow
  2️⃣ Nhắn tin mã này cho Bé Tiền trên Zalo: BT-A7K3P2
  (Mã hết hạn sau 10 phút)"

[User gửi "BT-A7K3P2" cho Zalo OA]
→ Zalo webhook → match token → link user
→ Telegram: "✅ Đã liên kết Zalo thành công!"
→ Zalo:     "✅ Xin chào! Bé Tiền đã kết nối. Bạn sẽ nhận thông báo cashflow tại đây."
```

**Acceptance criteria:**
- Token expires 10 phút
- Token single-use (thứ 2 dùng lại → error friendly)
- Confirmation gửi cả 2 kênh
- `/unlink_zalo` → clear `zalo_user_id`, confirm in Telegram
- `/profile` hiển thị "Zalo: đã liên kết" nếu linked

---

### S24: Cashflow Alert via Zalo

**Extend `get_notifiers()`:**
```python
async def get_notifiers(user_id: UUID) -> List[Notifier]:
    user = await user_service.get(user_id)
    notifiers: List[Notifier] = [get_telegram_notifier(user)]
    if user.zalo_user_id:
        notifiers.append(ZaloNotifier(
            client=get_zalo_oa_client(),
            zalo_user_id=user.zalo_user_id,
        ))
    return notifiers
```

**`cashflow/alert.py` đã dùng `get_notifiers()` từ S17** → tự động multi-channel khi Zalo linked.

**Zalo message format** (shorter than Telegram):
```
⚠️ Tháng 9/2026: số dư có thể xuống ~12 triệu
(dưới ngưỡng an toàn 15 triệu bạn đặt)

Xem chi tiết: [link]
```

**Acceptance criteria:**
- Linked user nhận alert cả Telegram + Zalo
- Unlinked user chỉ nhận Telegram
- Zalo fail → Telegram vẫn gửi (fail-open)
- Zalo message ≤ 300 chars, plain text
- No duplicate content trong cùng kênh

---

## Database Schema Summary

### New Tables

| Table | Purpose | Epic |
|---|---|---|
| `life_events` | User life milestones với cost parameters | 2 |
| `recurring_patterns` | Auto-detected recurring income/expense | 3 |
| `cashflow_forecasts` | 3-month cashflow forecasts (JSONB) | 3 |
| `zalo_link_tokens` | Temporary tokens for Zalo linking | 4 |

### Modified Tables

| Table | Change | Epic |
|---|---|---|
| `twin_projections` | `+ actual_net_worth NUMERIC(20,2)` | 1 |
| `users` | `+ zalo_user_id VARCHAR(50)` | 4 |
| `users` | `+ cashflow_alert_threshold NUMERIC(20,2)` | 3 |

---

## New Module Structure

```
finance_assistant/backend/
├── twin/                          # Phase 4A — extended in 4B
│   ├── engine/
│   │   ├── monte_carlo.py         # Extended: calls apply_life_events()
│   │   └── life_events.py         # NEW (S8): life event path injection
│   └── accuracy.py                # NEW (S1): historical accuracy tracking
│
├── cashflow/                      # NEW module (Phase 4B)
│   ├── __init__.py
│   ├── detector.py                # S14: recurring pattern detection
│   ├── forecast.py                # S16: 3-month cashflow forecast
│   ├── alert.py                   # S17: low-balance alert engine
│   ├── chart.py                   # S18: waterfall chart renderer
│   └── scheduler.py               # weekly re-detect + daily forecast update
│
├── life_events/                   # NEW module (Phase 4B)
│   ├── __init__.py
│   ├── models.py
│   ├── service.py
│   ├── presets.py                 # S7: VN life event defaults
│   └── handlers.py                # S9: Telegram conversation handlers
│
└── adapters/
    ├── zalo_oa.py                 # NEW (S21): ZaloOAClient
    └── zalo_notifier.py           # NEW (S22): ZaloNotifier(Notifier)
```

---

## Performance Targets

| Operation | p95 Target |
|---|---|
| Life event MC injection (5 events, 1000 paths, 240 months) | < 500ms |
| Cashflow forecast compute | < 200ms |
| Cashflow waterfall chart PNG | < 500ms |
| Twin impact chart PNG (before/after) | < 500ms |
| Mini App "Kế hoạch" tab load | < 1s |
| Mini App life event toggle re-render | < 500ms |
| Zalo message send (external API) | < 2s |
| Recurring pattern detection (500 tx) | < 2s |

---

## Trust & Persona Guidelines

### Cashflow Alert Tone
- DÙNG: "có thể", "dự báo", "ước tính", "xu hướng"
- TRÁNH: "chắc chắn", "sẽ xảy ra", "cảnh báo nguy hiểm", "thất bại tài chính"
- Luôn có gợi ý hành động cụ thể đi kèm alert

### Life Event Narrative Tone
- Mua nhà/Kết hôn/Con cái: **không bao giờ** gợi ý trì hoãn vì lý do tài chính
- Impact luôn đi kèm frame: "trade-off bình thường" hoặc "hoàn toàn có thể plan được"
- Gợi ý hành động: cụ thể, số tiền rõ ràng, không chung chung

### Zalo Channel Tone
- Ngắn hơn Telegram (mobile notification-first)
- Plain text, không Markdown
- Tối đa 2 emoji per message
- ≤ 300 chars (Zalo display limit)

---

## Critical Path

```
Week 1: Epic 1 (Twin Polish — S1-S5, có thể parallel)
         Epic 2 S6+S7 (Life Event model + presets)
         Epic 3 S14 (Recurring detector — start data work early)

Week 2: Epic 2 S8 (MC integration — critical path for Epic 2)
         Epic 3 S15+S16 (User review flow + forecast model)
         Epic 4 S21+S22 (Zalo SDK + ZaloNotifier — setup work)

Week 3: Epic 2 S9+S11 parallel (Telegram flow + Mini App panel)
         Epic 3 S17+S18+S19+S20 parallel (alert + charts + briefing + mini app)
         Epic 4 S23 (Zalo linking flow)

Week 4: Epic 2 S10+S12+S13 (charts + narrative + tests)
         Epic 4 S24 (Cashflow alert via Zalo)
         Polish + regression tests + benchmark
```

---

## Definition of Done

- [ ] Tất cả 24 stories implemented với acceptance criteria passed
- [ ] `uv run pytest` passes — no regressions
- [ ] `uv run ruff check .` clean
- [ ] `layer-contract-checker` agent: không vi phạm layer contract
- [ ] `vi-localization-checker` agent: không có hardcoded Vietnamese strings
- [ ] Performance benchmarks đạt tất cả targets
- [ ] `phase-4B-benchmark.md` updated với actual numbers
- [ ] `phase-4B-deploy-announcements.md` ready
- [ ] `phase-status.yaml` updated: Phase 4A → done, Phase 4B → current/done
