# Phase 3.8 — Wealth Completion (Chi Tiết Triển Khai)

> **Đây là phase foundation hoàn thiện trước Twin — fill những gaps về data còn thiếu để Phase 4 (Twin) có thể compute meaningful predictions.**

> **Thời gian ước tính:** 2 tuần (với Claude Code velocity)  
> **Mục tiêu cuối Phase:** Sản phẩm có đầy đủ rental tracking, multi-income, recurring transactions với reminders, basic cashflow forecasting, và goals management complete.  
> **Điều kiện "Done":** User có thể track 100% income/expense flows, get reminders cho recurring expenses, see 3-month cashflow forecast, set goals từ templates với projection.

> **Prerequisites:** Phase 3.7 (agent architecture) đã ship. Phase 3.8 leverage Phase 3.7 tools — extend chúng với rental + income data.

---

## 🎯 Triết Lý Thiết Kế Phase 3.8

Đây là 6 nguyên lý quan trọng, đọc kỹ trước khi code:

### 1. "Foundation Before Flash"
Phase 4 (Twin) cần predict tương lai. Predict cần complete data. Hiện tại agent đang query trên incomplete data (no rental, single income, no recurring patterns) → mọi prediction sẽ bị skewed. Phase 3.8 fix root cause.

### 2. "Reuse Phase 3.7 Tools, Don't Reinvent"
Phase 3.7 có 5 tools (get_assets, get_transactions, etc.). Phase 3.8 **mở rộng tools này** để hiểu rental income, multi-income types — không tạo agent mới hay parallel system.

### 3. "Reminders Are Hooks"
User asked specifically cho reminders về recurring expenses. Đây không chỉ là utility feature — **mỗi reminder = 1 daily touchpoint với app** = retention driver. Treat reminders as engagement strategy, not just todos.

### 4. "Templates > Wizards for Goals"
User chose câu 4 = c (templates) and a (single-goal focus). Reasoning: most user goals fall into 5-7 patterns (mua xe, mua nhà, du lịch, hưu trí, học vấn, đám cưới, quỹ khẩn cấp). Templates faster than blank wizard.

### 5. "Cashflow Forecast = Twin Foundation"
This phase's cashflow forecasting (simple v1) is **the seed** for Phase 4 Twin projections. Build it correctly now.

### 6. "Case A Only — Don't Overengineer Rental"
User chose Case A only (chủ nhà). Don't build Case B complexity (nhà thuê ở) — that's just `recurring_expense` with category="housing". Avoid feature creep.

---

## 📅 Phân Bổ Thời Gian (2 tuần)

| Tuần | Nội dung | Deliverable |
|------|----------|-------------|
| **Tuần 1** | Rental + Multi-Income + Recurring (foundation data) | New data models live, AI agent updated |
| **Tuần 2** | Cashflow Forecast + Goals Management + Reminders | Complete UX, ready for Twin foundation |

---

## 🗂️ Cấu Trúc Thư Mục Mở Rộng

```
finance_assistant/
├── app/
│   ├── wealth/                          # Existing from Phase 3A
│   │   ├── models/
│   │   │   ├── asset.py                 # ⭐ EXTEND - add is_rental, rental_metadata
│   │   │   └── ...
│   │   └── services/
│   │       ├── rental_service.py        # ⭐ NEW
│   │       └── ...
│   │
│   ├── income/                          # ⭐ NEW MODULE
│   │   ├── models/
│   │   │   └── income_stream.py
│   │   ├── services/
│   │   │   ├── income_service.py
│   │   │   └── recurring_detector.py
│   │   └── schemas.py
│   │
│   ├── transactions/                    # Existing
│   │   ├── models/
│   │   │   └── transaction.py           # ⭐ EXTEND - add is_recurring, recurrence_id
│   │   └── services/
│   │       ├── recurring_service.py     # ⭐ NEW
│   │       └── reminder_scheduler.py    # ⭐ NEW
│   │
│   ├── cashflow/                        # ⭐ NEW MODULE
│   │   ├── services/
│   │   │   ├── forecaster.py            # Simple v1 forecasting
│   │   │   └── runway_analyzer.py
│   │   └── schemas.py
│   │
│   ├── goals/                           # ⭐ ENHANCE EXISTING
│   │   ├── models/
│   │   │   └── goal.py                  # ⭐ EXTEND - templates, projection
│   │   ├── services/
│   │   │   ├── goal_service.py
│   │   │   ├── template_service.py      # ⭐ NEW
│   │   │   └── projection_service.py    # ⭐ NEW
│   │   └── templates/
│   │       └── goal_templates.yaml      # ⭐ NEW - 7 preset goals
│   │
│   └── agent/                           # Existing from Phase 3.7
│       └── tools/
│           ├── get_assets.py            # ⭐ EXTEND - support rental filter
│           ├── get_income.py            # ⭐ NEW
│           ├── forecast_cashflow.py     # ⭐ NEW
│           └── get_goals.py             # ⭐ NEW
│
├── content/
│   ├── goal_templates.yaml              # ⭐ NEW
│   └── reminder_templates.yaml          # ⭐ NEW
│
└── tests/
    └── test_phase_3_8/
        ├── test_rental.py
        ├── test_income.py
        ├── test_recurring.py
        ├── test_cashflow_forecast.py
        ├── test_goals.py
        └── test_reminders.py
```

---

# 🔧 TUẦN 1: Foundation Data (Rental + Income + Recurring)

## 1.1 — Component 1: Rental Property Tracking (Case A)

### Data Model Extension

#### File: `app/wealth/models/asset.py` (extend existing)

```python
# Existing Asset model + extension
from sqlalchemy import Column, Integer, String, Decimal, Boolean, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

class Asset(Base):
    # ... existing fields ...
    
    # NEW for rental tracking
    is_rental = Column(Boolean, default=False, nullable=False)
    rental_metadata = Column(JSON, nullable=True)
    # rental_metadata structure:
    # {
    #   "monthly_rent": 15000000,        # VND
    #   "occupancy_status": "rented",    # "rented" | "vacant" | "self_use"
    #   "tenant_name": "Anh Tuan",       # optional
    #   "lease_start_date": "2024-01-01",
    #   "lease_end_date": "2025-12-31",
    #   "monthly_expenses": 1500000,     # tax, maintenance, agent
    #   "deposit_held": 30000000,        # tenant deposit
    # }
```

### Schema (Pydantic)

#### File: `app/wealth/schemas.py` (extend)

```python
from pydantic import BaseModel
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

class RentalMetadata(BaseModel):
    monthly_rent: Decimal
    occupancy_status: Literal["rented", "vacant", "self_use"]
    tenant_name: Optional[str] = None
    lease_start_date: Optional[date] = None
    lease_end_date: Optional[date] = None
    monthly_expenses: Decimal = Decimal("0")
    deposit_held: Decimal = Decimal("0")
    
    @property
    def net_monthly_yield(self) -> Decimal:
        """Net rental income after expenses."""
        return self.monthly_rent - self.monthly_expenses
    
    @property
    def annual_yield_pct(self, property_value: Decimal) -> float:
        """Annual yield as % of property value."""
        if property_value == 0:
            return 0
        annual_net = float(self.net_monthly_yield * 12)
        return (annual_net / float(property_value)) * 100
```

### Service Layer

#### File: `app/wealth/services/rental_service.py`

```python
class RentalService:
    """Manage rental properties — Case A (landlord perspective)."""
    
    async def mark_as_rental(
        self,
        asset_id: int,
        rental_metadata: RentalMetadata,
    ) -> Asset:
        """Convert existing real_estate asset to rental property."""
        asset = await self._get_asset(asset_id)
        if asset.asset_type != "real_estate":
            raise ValueError("Only real_estate assets can be marked as rental")
        
        asset.is_rental = True
        asset.rental_metadata = rental_metadata.model_dump(mode="json")
        await self._save(asset)
        
        # Auto-create recurring income transaction
        await self._setup_recurring_rental_income(asset, rental_metadata)
        
        return asset
    
    async def update_occupancy(
        self,
        asset_id: int,
        new_status: str,
        effective_date: date = None,
    ):
        """Update rental status (e.g., tenant moved out)."""
        # Pause/resume recurring income accordingly
        pass
    
    async def get_rental_yield_summary(self, user_id: int) -> dict:
        """Aggregate rental income across all properties."""
        rentals = await self._get_user_rentals(user_id)
        
        total_monthly_rent = sum(r.rental_metadata["monthly_rent"] for r in rentals)
        total_monthly_expenses = sum(r.rental_metadata["monthly_expenses"] for r in rentals)
        net_monthly = total_monthly_rent - total_monthly_expenses
        
        return {
            "property_count": len(rentals),
            "occupied_count": sum(1 for r in rentals if r.rental_metadata["occupancy_status"] == "rented"),
            "total_monthly_rent": total_monthly_rent,
            "total_monthly_expenses": total_monthly_expenses,
            "net_monthly_yield": net_monthly,
            "annual_passive_income": net_monthly * 12,
        }
```

### Wizard Integration (Bot)

When user adds real_estate asset, ask:
- "Đây có phải là BĐS cho thuê không?" [Có] [Không]
- If yes: collect rental metadata via inline keyboard wizard:
  - Tiền thuê hàng tháng: text input
  - Chi phí (thuế, sửa chữa) hàng tháng: text input
  - Trạng thái: [Đang cho thuê] [Trống]
  - Nếu đang cho thuê: thông tin thêm? [Skip] [Thêm]

---

## 1.2 — Component 2: Multi-Income Streams

### Data Model

#### File: `app/income/models/income_stream.py`

```python
class IncomeStream(Base):
    __tablename__ = "income_streams"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Stream identification
    name = Column(String(200), nullable=False)
    stream_type = Column(String(50), nullable=False)  # "salary", "freelance", "dividend", "rental", "interest", "other"
    is_passive = Column(Boolean, default=False)
    
    # Amount + schedule
    amount = Column(Decimal(20, 2), nullable=False)
    currency = Column(String(10), default="VND")
    
    schedule_type = Column(String(20), nullable=False)  # "monthly", "quarterly", "annually", "ad_hoc"
    schedule_day = Column(Integer, nullable=True)  # day of month (1-31) for monthly
    schedule_month = Column(Integer, nullable=True)  # month for quarterly/annually
    
    # Lifecycle
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)  # null = ongoing
    is_active = Column(Boolean, default=True)
    
    # Optional: link to source
    source_asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True)  # for dividends, rental income
    
    # Metadata
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

### Income Type Classifications

```yaml
# Income types and their characteristics
income_types:
  salary:
    label: "Lương"
    is_passive: false
    typical_schedule: "monthly"
    examples: ["Lương cứng", "Lương + thưởng"]
  
  freelance:
    label: "Freelance / Công việc thêm"
    is_passive: false
    typical_schedule: "ad_hoc"
    examples: ["Project", "Consulting", "Side gig"]
  
  dividend:
    label: "Cổ tức"
    is_passive: true
    typical_schedule: "annually"  # most VN stocks pay yearly
    examples: ["Cổ tức cổ phiếu"]
  
  rental:
    label: "Thuê BĐS"
    is_passive: true
    typical_schedule: "monthly"
    auto_linked: true  # auto-created from rental properties
  
  interest:
    label: "Lãi tiết kiệm"
    is_passive: true
    typical_schedule: "monthly"  # or maturity-based
    examples: ["Tiền gửi ngân hàng"]
  
  other:
    label: "Khác"
    is_passive: false
    typical_schedule: "ad_hoc"
```

### Service

```python
class IncomeService:
    async def add_income_stream(self, user_id, stream_data) -> IncomeStream:
        """Add a new income stream."""
        pass
    
    async def get_total_monthly_income(self, user_id) -> dict:
        """Aggregate all income streams normalized to monthly."""
        streams = await self._get_active_streams(user_id)
        
        total = Decimal(0)
        breakdown = {"active": Decimal(0), "passive": Decimal(0)}
        
        for stream in streams:
            monthly_amount = self._normalize_to_monthly(stream)
            total += monthly_amount
            
            if stream.is_passive:
                breakdown["passive"] += monthly_amount
            else:
                breakdown["active"] += monthly_amount
        
        return {
            "total_monthly": total,
            "active_income": breakdown["active"],
            "passive_income": breakdown["passive"],
            "passive_ratio": (breakdown["passive"] / total * 100) if total > 0 else 0,
            "stream_count": len(streams),
        }
    
    def _normalize_to_monthly(self, stream: IncomeStream) -> Decimal:
        """Convert any schedule to monthly equivalent."""
        if stream.schedule_type == "monthly":
            return stream.amount
        elif stream.schedule_type == "quarterly":
            return stream.amount / 3
        elif stream.schedule_type == "annually":
            return stream.amount / 12
        elif stream.schedule_type == "ad_hoc":
            # Average over last 6 months of actual receipts
            return self._compute_adhoc_average(stream)
        return Decimal(0)
```

### Wizard Integration

When user adds income via menu:
- "Loại thu nhập?" [Lương] [Freelance] [Cổ tức] [Thuê nhà] [Lãi] [Khác]
- "Số tiền?" → text
- "Bao lâu nhận 1 lần?" [Hàng tháng] [Hàng quý] [Hàng năm] [Bất định]
- If monthly: "Ngày nào trong tháng?" → number 1-31
- "Ngày bắt đầu?" → date picker

---

## 1.3 — Component 3: Recurring Transactions + Reminders

### Concept

**2 types of "recurring":**

1. **Auto-detected recurring** — Bot patterns thấy user chi same amount cùng category nhiều tháng → suggest "Có phải khoản này hàng tháng không?"

2. **Manually-marked recurring** — User explicitly tells bot "hàng tháng tôi trả thuê 15tr" → bot remembers + reminds.

### Data Model

#### File: `app/transactions/models/transaction.py` (extend)

```python
class Transaction(Base):
    # ... existing fields ...
    
    # NEW for recurring
    is_recurring = Column(Boolean, default=False)
    recurrence_id = Column(Integer, ForeignKey("recurring_patterns.id"), nullable=True)
```

#### File: `app/transactions/models/recurring_pattern.py`

```python
class RecurringPattern(Base):
    __tablename__ = "recurring_patterns"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Pattern
    name = Column(String(200), nullable=False)  # "Thuê nhà", "Điện nước", "Netflix"
    category = Column(String(50), nullable=False)
    expected_amount = Column(Decimal(20, 2), nullable=False)
    amount_variance_pct = Column(Float, default=10.0)  # ± tolerance for matching
    
    # Schedule
    schedule_type = Column(String(20), default="monthly")
    expected_day_of_month = Column(Integer, nullable=True)  # 1-31
    
    # State
    is_active = Column(Boolean, default=True)
    auto_detected = Column(Boolean, default=False)  # True if bot detected
    user_confirmed = Column(Boolean, default=False)  # True if user confirmed
    
    # Reminders
    enable_reminders = Column(Boolean, default=True)
    reminder_days_before = Column(Integer, default=2)  # days before expected_day to remind
    last_reminder_sent = Column(Date, nullable=True)
    
    # Tracking
    last_occurrence_date = Column(Date, nullable=True)
    occurrence_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
```

### Auto-Detection Algorithm

#### File: `app/transactions/services/recurring_detector.py`

```python
class RecurringDetector:
    """Detect recurring transaction patterns from history."""
    
    async def detect_patterns(self, user_id: int) -> list[dict]:
        """Run nightly. Find new recurring patterns to suggest."""
        # Get last 6 months of transactions
        transactions = await self._get_user_transactions_last_n_months(user_id, 6)
        
        # Group by (category, amount range)
        groups = self._group_similar(transactions)
        
        suggestions = []
        for key, group_txns in groups.items():
            if self._looks_recurring(group_txns):
                suggestions.append({
                    "category": key[0],
                    "amount": key[1],
                    "occurrences": len(group_txns),
                    "typical_day": self._compute_typical_day(group_txns),
                    "merchant_hint": self._most_common_merchant(group_txns),
                })
        
        return suggestions
    
    def _looks_recurring(self, transactions: list) -> bool:
        """Heuristic: 3+ occurrences with monthly cadence."""
        if len(transactions) < 3:
            return False
        
        # Sort by date
        dates = sorted([t.date for t in transactions])
        
        # Check intervals
        intervals = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
        avg_interval = sum(intervals) / len(intervals)
        
        # Monthly = ~30 days, with variance
        return 25 <= avg_interval <= 35
    
    async def suggest_to_user(self, user_id: int):
        """Send Telegram message asking user to confirm pattern."""
        suggestions = await self.detect_patterns(user_id)
        
        for s in suggestions[:3]:  # Top 3 to avoid spam
            await self._send_pattern_suggestion(user_id, s)
```

### Reminder Scheduler

#### File: `app/transactions/services/reminder_scheduler.py`

```python
class ReminderScheduler:
    """Send reminders for upcoming recurring expenses."""
    
    async def run_daily(self):
        """Run via cron at 9 AM. Send reminders for due-soon patterns."""
        today = date.today()
        
        # Get all active patterns with reminders enabled
        patterns = await self._get_due_soon_patterns(today)
        
        for pattern in patterns:
            await self._send_reminder(pattern)
    
    async def _send_reminder(self, pattern: RecurringPattern):
        """Send Telegram reminder."""
        days_until = (pattern.next_expected_date - date.today()).days
        
        message = self._format_reminder(pattern, days_until)
        
        await telegram_bot.send_message(
            chat_id=pattern.user.telegram_chat_id,
            text=message,
            reply_markup=self._reminder_keyboard(pattern),
        )
        
        pattern.last_reminder_sent = date.today()
        await self._save(pattern)
    
    def _format_reminder(self, pattern, days_until):
        if days_until == 0:
            urgency = "Hôm nay"
        elif days_until == 1:
            urgency = "Ngày mai"
        else:
            urgency = f"{days_until} ngày nữa"
        
        return (
            f"⏰ Nhắc nhẹ — {urgency} là tới hạn:\n\n"
            f"💸 **{pattern.name}**\n"
            f"📅 Dự kiến: {pattern.next_expected_date.strftime('%d/%m')}\n"
            f"💰 Khoảng {pattern.expected_amount:,.0f}đ\n\n"
            f"Bạn đã trả chưa?"
        )
    
    def _reminder_keyboard(self, pattern):
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Đã trả", callback_data=f"reminder:paid:{pattern.id}"),
                InlineKeyboardButton("⏭️ Trễ vài ngày", callback_data=f"reminder:delay:{pattern.id}"),
            ],
            [
                InlineKeyboardButton("🔕 Tắt nhắc nhở", callback_data=f"reminder:disable:{pattern.id}"),
            ],
        ])
```

### User Flow

**Auto-detection flow (user passive):**
1. User chi 15tr cho "thuê nhà" tháng 5/2025, 6/2025, 7/2025
2. Detector job phát hiện pattern
3. Sends: "Bạn có phải trả thuê nhà 15tr hàng tháng không? [Có, ngày 5] [Không]"
4. User confirm → RecurringPattern saved
5. Day 3 of next month: reminder sent

**Manual flow (user active):**
1. User send: "/recurring add" hoặc qua menu
2. Wizard: "Tên?" → "Thuê nhà"
3. "Số tiền?" → "15tr"
4. "Hàng tháng vào ngày nào?" → "5"
5. Confirm → Pattern + reminder setup

---

## ✅ Checklist Cuối Tuần 1

- [ ] Asset model extended with `is_rental` + `rental_metadata` JSON
- [ ] RentalService working (mark, update, summary)
- [ ] Asset wizard updated to ask "Đây có phải BĐS cho thuê?"
- [ ] IncomeStream model + service
- [ ] Income wizard collects type, amount, schedule
- [ ] RecurringPattern model
- [ ] RecurringDetector job runs nightly
- [ ] Auto-detection sends suggestions
- [ ] Manual recurring entry via /recurring command
- [ ] ReminderScheduler runs daily at 9 AM
- [ ] Reminders sent with action buttons (paid/delay/disable)
- [ ] Phase 3.7 agent tools updated to query rental + income data

---

# 🎨 TUẦN 2: Forecasting + Goals + Polish

## 2.1 — Component 4: Cashflow Forecasting (Simple v1)

### Methodology

**Simple Average Method:**
```
For each future month M:
  expected_income(M) = average(income, last 3 months)
  expected_expense(M) = average(expense, last 3 months)
  expected_savings(M) = expected_income(M) - expected_expense(M)
  
  + Add known recurring transactions (high confidence)
  + Add scheduled income (salary day, dividend dates)
```

Why simple: reliable, no ML complexity, foundation for v2 pattern-based later.

### Service

#### File: `app/cashflow/services/forecaster.py`

```python
class CashflowForecaster:
    """Simple v1: project 3-6 months ahead based on averages + recurring."""
    
    async def forecast(
        self,
        user_id: int,
        months_ahead: int = 3,
    ) -> list[MonthlyForecast]:
        # Step 1: Compute baseline averages from last 3 months
        baseline = await self._compute_baseline(user_id)
        
        # Step 2: Get all recurring patterns
        recurring_income = await IncomeService().get_active_streams(user_id)
        recurring_expenses = await RecurringService().get_active_patterns(user_id)
        
        # Step 3: Project month by month
        forecasts = []
        for month_offset in range(1, months_ahead + 1):
            target_month = self._month_offset(month_offset)
            
            forecast = MonthlyForecast(
                month=target_month,
                expected_income=self._compute_expected_income(target_month, recurring_income, baseline),
                expected_expense=self._compute_expected_expense(target_month, recurring_expenses, baseline),
                confidence=self._compute_confidence(month_offset),  # decays with distance
            )
            forecast.expected_savings = forecast.expected_income - forecast.expected_expense
            
            forecasts.append(forecast)
        
        return forecasts
    
    def _compute_confidence(self, month_offset: int) -> float:
        """Confidence decreases with distance."""
        # Month 1: 85%, Month 2: 70%, Month 3: 55%, Month 4: 40%
        return max(0.3, 1.0 - (month_offset * 0.15))
```

### Output Format

```python
class MonthlyForecast(BaseModel):
    month: date  # first day of month
    expected_income: Decimal
    expected_expense: Decimal
    expected_savings: Decimal
    confidence: float  # 0-1
    breakdown: dict  # for explainability
    notes: list[str]  # warnings, e.g., "Tháng 7: dự kiến chi điện cao do mùa hè"
```

### Runway Analysis

```python
class RunwayAnalyzer:
    """If user lost income, how long can they survive?"""
    
    async def compute_runway(self, user_id: int) -> dict:
        liquid_assets = await self._get_liquid_assets(user_id)  # cash + savings + bonds
        monthly_essential_expenses = await self._estimate_essential_expenses(user_id)
        
        if monthly_essential_expenses == 0:
            return {"months": float("inf"), "warning": None}
        
        runway_months = float(liquid_assets) / float(monthly_essential_expenses)
        
        warning = None
        if runway_months < 3:
            warning = "🚨 Runway dưới 3 tháng — nên build emergency fund"
        elif runway_months < 6:
            warning = "⚠️ Runway 3-6 tháng — okay nhưng có thể tốt hơn"
        
        return {
            "months": runway_months,
            "liquid_assets": liquid_assets,
            "monthly_burn": monthly_essential_expenses,
            "warning": warning,
        }
```

### Agent Tool Integration

#### File: `app/agent/tools/forecast_cashflow.py`

```python
class ForecastCashflowTool(Tool):
    """New Phase 3.7-style tool for forecasting queries."""
    
    @property
    def name(self): return "forecast_cashflow"
    
    @property
    def description(self):
        return (
            "Forecast user's cashflow for upcoming months. Use for queries like:\n"
            "- 'Tháng tới tôi sẽ tiết kiệm bao nhiêu?'\n"
            "- 'Dự đoán chi tiêu 3 tháng tới'\n"
            "- 'Khi nào tôi sẽ âm tài khoản?' (runway)"
        )
    
    # ... full implementation
```

---

## 2.2 — Component 5: Goals Management Complete

### Goal Templates

#### File: `content/goal_templates.yaml`

```yaml
templates:
  - id: "buy_car"
    name: "Mua xe"
    category: "vehicle"
    icon: "🚗"
    typical_amount_range: [200000000, 1500000000]  # 200tr-1.5 tỷ
    typical_timeline_months: [12, 60]
    suggested_questions:
      - "Loại xe nào? (sedan/SUV/xe máy)"
      - "Mua mới hay cũ?"
    
  - id: "buy_house"
    name: "Mua nhà"
    category: "housing"
    icon: "🏠"
    typical_amount_range: [1500000000, 10000000000]
    typical_timeline_months: [36, 120]
    suggested_questions:
      - "Khu vực nào?"
      - "Trả 1 lần hay vay ngân hàng?"
    
  - id: "travel"
    name: "Du lịch"
    category: "travel"
    icon: "✈️"
    typical_amount_range: [10000000, 200000000]
    typical_timeline_months: [3, 24]
    
  - id: "retirement"
    name: "Hưu trí"
    category: "retirement"
    icon: "🌅"
    typical_amount_range: [3000000000, 20000000000]
    typical_timeline_months: [120, 360]  # 10-30 years
    
  - id: "education"
    name: "Học vấn"
    category: "education"
    icon: "🎓"
    typical_amount_range: [50000000, 1000000000]
    typical_timeline_months: [12, 60]
    
  - id: "wedding"
    name: "Đám cưới"
    category: "life_event"
    icon: "💒"
    typical_amount_range: [200000000, 1000000000]
    typical_timeline_months: [6, 24]
    
  - id: "emergency_fund"
    name: "Quỹ khẩn cấp"
    category: "safety"
    icon: "🛡️"
    typical_amount_range: [50000000, 500000000]
    typical_timeline_months: [6, 24]
    description: "6 tháng chi tiêu cố định"
```

### Goal Model

```python
class Goal(Base):
    __tablename__ = "goals"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # From template
    template_id = Column(String(50), nullable=True)  # "buy_car", etc.
    name = Column(String(200), nullable=False)
    icon = Column(String(20))
    
    # Target
    target_amount = Column(Decimal(20, 2), nullable=False)
    target_date = Column(Date, nullable=True)  # null = open-ended
    
    # Progress
    current_amount = Column(Decimal(20, 2), default=0)
    
    # Strategy (computed)
    monthly_savings_required = Column(Decimal(20, 2), nullable=True)  # cached
    
    # State
    status = Column(String(20), default="active")  # active, completed, paused, abandoned
    priority = Column(Integer, default=5)  # 1=highest, 10=lowest (for multi-goal future)
    
    # Linkage
    linked_assets = Column(JSON, nullable=True)  # asset IDs that count toward this
    
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
```

### Projection Service

```python
class GoalProjectionService:
    """Compute timeline + monthly savings required for goals."""
    
    async def project_goal(self, goal_id: int) -> dict:
        goal = await self._get_goal(goal_id)
        
        # Current state
        remaining = goal.target_amount - goal.current_amount
        
        # Get user's actual saving rate from last 3 months
        avg_monthly_savings = await self._get_avg_monthly_savings(goal.user_id)
        
        # Methods
        result = {
            "goal_id": goal_id,
            "remaining_amount": remaining,
            "current_progress_pct": float(goal.current_amount / goal.target_amount * 100),
        }
        
        # If target_date set, compute required monthly savings
        if goal.target_date:
            months_remaining = self._months_between(date.today(), goal.target_date)
            if months_remaining > 0:
                result["months_remaining"] = months_remaining
                result["required_monthly_savings"] = remaining / months_remaining
                result["feasibility"] = self._assess_feasibility(
                    result["required_monthly_savings"],
                    avg_monthly_savings,
                )
        
        # If no target_date, compute "if save X/month, will reach in Y months"
        if not goal.target_date and avg_monthly_savings > 0:
            months_to_reach = remaining / avg_monthly_savings
            result["estimated_completion_months"] = months_to_reach
            result["estimated_completion_date"] = self._add_months(date.today(), months_to_reach)
        
        return result
    
    def _assess_feasibility(self, required: Decimal, actual: Decimal) -> str:
        ratio = float(required / actual) if actual > 0 else float("inf")
        
        if ratio <= 0.5: return "easy"        # current saving 2x+ what's needed
        elif ratio <= 1.0: return "feasible"  # current saving ≥ required
        elif ratio <= 1.5: return "stretch"   # need 1.5x current saving
        elif ratio <= 2.0: return "ambitious" # need 2x
        else: return "needs_revision"          # >2x — unrealistic
```

### Goal CRUD via Telegram

**Add goal flow:**
```
User taps Mục tiêu → Thêm mục tiêu (from Phase 3.6 menu)
Bot: "Bạn muốn đặt mục tiêu gì? Chọn template hoặc tự tạo:"
[🚗 Mua xe] [🏠 Mua nhà] [✈️ Du lịch]
[🌅 Hưu trí] [🎓 Học vấn] [💒 Đám cưới]
[🛡️ Quỹ khẩn cấp] [✏️ Tự tạo]

User taps [🚗 Mua xe]
Bot: "Số tiền mục tiêu?" → user types "800tr"
Bot: "Khi nào muốn đạt được? (Để trống nếu không định)"
[6 tháng] [1 năm] [2 năm] [3 năm] [Tự nhập] [Bỏ qua]

User taps [2 năm]
Bot calculates: Need 800tr / 24 = ~33tr/tháng
Bot: "Để đạt mục tiêu này, bạn cần tiết kiệm ~33tr/tháng.

Mức tiết kiệm hiện tại của bạn: ~8tr/tháng.
Đánh giá: Khó đạt với rate hiện tại 🤔

Bạn có thể:
1. Lùi target sang 6 năm (~11tr/tháng)
2. Tăng saving rate hoặc đầu tư
3. Giảm target amount

Bạn vẫn muốn save target này chứ?"
[✅ Có, tôi sẽ cố] [📅 Lùi target] [💰 Giảm amount]
```

### Goal Tool for Agent

```python
class GetGoalsTool(Tool):
    """Phase 3.7-style tool for goals queries."""
    
    @property
    def description(self):
        return (
            "Get user's goals with progress and projections. Examples:\n"
            "- 'mục tiêu của tôi'\n"
            "- 'cần bao lâu để đạt mục tiêu mua xe?'\n"
            "- 'tiến độ đạt mục tiêu'"
        )
```

---

## ✅ Checklist Cuối Tuần 2

- [ ] CashflowForecaster (simple average method)
- [ ] RunwayAnalyzer with warnings
- [ ] ForecastCashflowTool registered with agent
- [ ] Goal templates loaded from YAML (7 templates)
- [ ] Goal CRUD via Telegram menu (from Phase 3.6)
- [ ] GoalProjectionService computes feasibility
- [ ] GetGoalsTool registered with agent
- [ ] Phase 3.6 menu actions Mục tiêu now functional (not stub)
- [ ] Test: User creates "Mua xe" goal → sees feasibility analysis
- [ ] Test: User asks "tháng tới tiết kiệm bao nhiêu?" → forecast response

---

# 🎯 Exit Criteria Phase 3.8

Phase 3.8 ready to ship when:

- [ ] Rental property can be marked + tracked + yields computed
- [ ] User can add multiple income streams (5+ types)
- [ ] Recurring transactions auto-detected from history
- [ ] Recurring transactions can be manually added
- [ ] Reminders sent for upcoming recurring (with paid/delay/disable buttons)
- [ ] Cashflow forecast for next 3 months available via agent query
- [ ] Goals creatable from 7 templates
- [ ] Goal projections show monthly savings required + feasibility
- [ ] All Phase 3.7 agent queries about new data work correctly
- [ ] No regressions in existing flows
- [ ] Test suite passes (rental, income, recurring, forecast, goals)

---

# 🚧 Bẫy Thường Gặp Phase 3.8

## 1. Rental income double-counting
User has rental property → IncomeStream auto-created. But user also manually marks transaction "thuê nhà thu được". → Don't double-count. Auto-link manual transactions to recurring pattern.

## 2. Recurring detection too aggressive
3 lunches at same restaurant = "recurring"? No, that's pattern not commitment. Tune: only category-aware, only similar amounts (±10%), only 25-35 day intervals.

## 3. Forecast confidence over-claimed
User sees "Tháng 6: tiết kiệm 8.5tr" → expects exact. Frame: "Tháng 6 dự kiến: ~8tr (tin cậy 85%)".

## 4. Reminder spam
Multiple recurring patterns → multiple reminders → user annoyed. Bundle: "📋 Hôm nay có 3 khoản đến hạn: thuê nhà 15tr, internet 500k, gym 800k".

## 5. Goal feasibility too harsh
User sets ambitious goal → bot says "needs_revision" → demotivating. Frame supportively: "Mục tiêu này thử thách! Đây là 3 cách để đạt được..."

## 6. Templates too rigid
User wants goal "Mua máy ảnh" — không có template. Always offer "✏️ Tự tạo" option. Templates are starting points, not constraints.

---

# 📊 Metrics Phase 3.8

Track from Day 1:

**Adoption:**
- % users with rental property tracked (target: 5-10% of Mass Affluent)
- % users with multiple income streams (target: 30%+)
- % users with active recurring patterns (target: 60%+)
- % users with active goals (target: 50%+)

**Engagement:**
- Recurring reminder open rate (target: 70%+)
- Goals created per active user (target: 1.5+)
- Forecast queries per user per month (target: 3+)

**Quality:**
- Auto-detection accuracy (target: 80%+ user confirms)
- Goal feasibility prediction accuracy (post-hoc check)

---

**Phase 3.8 = foundation completion. Sau phase này, agent có complete picture của user's financial life. Twin (Phase 4) ready to build on solid ground. 💚🏗️**
