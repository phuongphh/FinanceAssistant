# Phase 3A — Wealth Foundation (Chi Tiết Triển Khai)

> **Đây là Phase 3A mới sau khi pivot sang Personal CFO positioning.**
> Phase 3 cũ ("Zero-Input Philosophy") đã được archive.

> **Thời gian ước tính:** 4 tuần  
> **Mục tiêu cuối Phase:** User có thể nhập tất cả tài sản (bất kỳ loại nào), xem net worth tăng/giảm hàng ngày, và nhận morning briefing cá nhân hóa mỗi sáng.  
> **Điều kiện "Done":** User test nói: *"Lần đầu tôi thấy tổng tài sản mình ở một chỗ"*. Ít nhất 5/7 user test mở bot xem net worth hàng ngày sau 1 tuần.

> **Prerequisites:** Phase 1 (rich UX) và Phase 2 (personality) đã stable. User đã trust bot qua personality. Đây là lúc ra mắt core value prop — wealth tracking.

---

## 🎯 Triết Lý Thiết Kế Phase 3A

Trước khi code, hiểu 4 nguyên lý này:

### 1. "Net Worth từ ngày đầu tiên"
Dù user chỉ có 10 triệu tiền mặt, họ vẫn có net worth. Design để **mọi user đều thấy giá trị ngay**, không cần đợi đủ giàu mới dùng.

### 2. "Quality over quantity" trong asset entry
Tốt hơn **5 loại tài sản chính xác** so với **50 loại ước lượng bừa**. Optimize cho manual entry easy, không cố automate integration ngay.

### 3. "Morning Briefing là retention driver"
Phase 3A success hay fail phụ thuộc vào morning briefing. Đây là lý do user mở app mỗi sáng. Invest đặc biệt vào trải nghiệm này.

### 4. "Threshold-based expense, không exhaustive tracking"
Người có tài sản không muốn ghi từng 50k. Chỉ track **>200k**. Khác biệt lớn với Money Lover.

---

## 📅 Phân Bổ Thời Gian 4 Tuần

| Tuần | Nội dung | Deliverable |
|------|----------|-------------|
| **Tuần 1** | Asset data model + Manual entry flow | User nhập được 5 loại asset, xem tổng |
| **Tuần 2** | Morning Briefing infrastructure | Bot gửi briefing 7h sáng, personalized |
| **Tuần 3** | Simple Storytelling Expense | Threshold-based, chi >200k track, <200k gộp |
| **Tuần 4** | Net Worth visualization + Polish + Testing | Mini App dashboard, charts, user testing |

---

## 🗂️ Cấu Trúc Thư Mục Mở Rộng

```
finance_assistant/
├── app/
│   ├── wealth/                        # ⭐ NEW - Core Phase 3A
│   │   ├── __init__.py
│   │   ├── models/
│   │   │   ├── asset.py               # Asset base model
│   │   │   ├── asset_types.py         # Cash, Stock, RealEstate, Crypto, Gold, Other
│   │   │   ├── asset_snapshot.py      # Daily historical values
│   │   │   └── income_stream.py       # Salary, dividend, interest (simple)
│   │   ├── services/
│   │   │   ├── net_worth_calculator.py
│   │   │   ├── asset_service.py
│   │   │   └── cashflow_service.py
│   │   ├── valuation/                 # Asset valuation logic
│   │   │   ├── base.py
│   │   │   ├── cash.py                # 1:1 valuation
│   │   │   ├── stock.py               # (Phase 3B integrate real prices)
│   │   │   ├── real_estate.py         # User-input value
│   │   │   ├── crypto.py              # (Phase 3B)
│   │   │   └── gold.py                # (Phase 3B)
│   │   └── ladder.py                  # User level detection
│   │
│   ├── bot/
│   │   ├── handlers/
│   │   │   ├── asset_entry.py         # ⭐ NEW
│   │   │   ├── morning_briefing.py    # ⭐ NEW
│   │   │   ├── storytelling.py        # ⭐ NEW (simplified)
│   │   │   └── net_worth_display.py   # ⭐ NEW
│   │   ├── formatters/
│   │   │   ├── wealth_formatter.py    # ⭐ NEW
│   │   │   └── briefing_formatter.py  # ⭐ NEW
│   │   ├── keyboards/
│   │   │   ├── asset_keyboard.py      # ⭐ NEW
│   │   │   └── briefing_keyboard.py   # ⭐ NEW
│   │   └── personality/
│   │       └── wealth_messages.py     # ⭐ NEW - ladder-aware messages
│   │
│   ├── miniapp/
│   │   ├── templates/
│   │   │   ├── net_worth_dashboard.html  # ⭐ NEW
│   │   │   └── asset_detail.html         # ⭐ NEW
│   │   └── static/
│   │       └── js/
│   │           └── wealth_charts.js      # ⭐ NEW
│   │
│   └── scheduled/
│       ├── morning_briefing_job.py    # ⭐ NEW - 7h sáng
│       └── daily_snapshot_job.py      # ⭐ NEW - 23h59 mỗi ngày
│
├── content/
│   ├── briefing_templates.yaml        # ⭐ NEW
│   ├── ladder_messages.yaml           # ⭐ NEW - messages per level
│   └── asset_categories.yaml          # ⭐ NEW - loại asset & metadata
│
└── alembic/versions/
    ├── xxx_create_assets.py
    ├── xxx_create_asset_snapshots.py
    ├── xxx_create_income_streams.py
    └── xxx_add_transaction_threshold_config.py
```

---

# 🏗️ TUẦN 1: Asset Data Model + Manual Entry

## 1.1 — Database Schema

### Migration 1: Assets table

```python
# alembic/versions/xxx_create_assets.py

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'assets',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        
        # Asset classification
        sa.Column('asset_type', sa.String(30), nullable=False),  # cash, stock, real_estate, crypto, gold, other
        sa.Column('subtype', sa.String(50), nullable=True),  # e.g., "house", "land" for real_estate
        
        # Identity
        sa.Column('name', sa.String(200), nullable=False),  # "Nhà Mỹ Đình", "VNM stock", "USDT on Binance"
        sa.Column('description', sa.Text, nullable=True),
        
        # Value tracking
        sa.Column('initial_value', sa.Numeric(20, 2), nullable=False),  # Giá mua/gốc
        sa.Column('current_value', sa.Numeric(20, 2), nullable=False),  # Giá hiện tại
        sa.Column('acquired_at', sa.Date, nullable=False),  # Ngày mua/có
        sa.Column('last_valued_at', sa.DateTime, default=sa.func.now()),
        
        # Metadata (flexible per asset type)
        sa.Column('metadata', sa.JSON, nullable=True),
        # For stock: {"ticker": "VNM", "quantity": 100, "exchange": "HOSE"}
        # For real_estate: {"area_sqm": 80, "address": "...", "case": "A/B/C"}
        # For crypto: {"symbol": "BTC", "quantity": 0.5, "wallet": "Binance"}
        # For gold: {"weight_gram": 10, "type": "SJC"}
        
        # Status
        sa.Column('is_active', sa.Boolean, default=True),  # False = user đã bán
        sa.Column('sold_at', sa.Date, nullable=True),
        sa.Column('sold_value', sa.Numeric(20, 2), nullable=True),
        
        # Tracking
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    op.create_index('idx_assets_user', 'assets', ['user_id', 'is_active'])
    op.create_index('idx_assets_type', 'assets', ['asset_type'])


def downgrade():
    op.drop_index('idx_assets_type', 'assets')
    op.drop_index('idx_assets_user', 'assets')
    op.drop_table('assets')
```

**Lý do design này:**
- **`metadata` JSON:** Mỗi loại asset có fields khác nhau, JSON giúp flexible mà không phải tạo 5 tables
- **`initial_value` + `current_value`:** Track được gain/loss
- **`is_active` + `sold_at`:** Soft delete — không xóa data, preserve history
- **`last_valued_at`:** Biết value đã cũ chưa → prompt user update

### Migration 2: Asset Snapshots (daily history)

```python
# alembic/versions/xxx_create_asset_snapshots.py

def upgrade():
    op.create_table(
        'asset_snapshots',
        sa.Column('id', sa.BigInteger, primary_key=True),
        sa.Column('asset_id', sa.Integer, sa.ForeignKey('assets.id'), nullable=False),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('snapshot_date', sa.Date, nullable=False),
        sa.Column('value', sa.Numeric(20, 2), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        # Sources: "user_input", "market_api", "interpolated"
        
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
    )
    
    op.create_index('idx_snapshots_user_date', 'asset_snapshots', ['user_id', 'snapshot_date'])
    op.create_unique_constraint(
        'uq_asset_date', 'asset_snapshots', ['asset_id', 'snapshot_date']
    )
```

**Tại sao cần snapshots:**
- Để vẽ chart "Net worth 30/90/365 ngày qua"
- Để tính "Tăng X% tháng này vs tháng trước"
- Historical record cho tax reports sau này
- Nếu user xóa asset → history vẫn còn

### Migration 3: Income Streams (Simplified)

```python
# alembic/versions/xxx_create_income_streams.py

def upgrade():
    op.create_table(
        'income_streams',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        
        sa.Column('source_type', sa.String(30), nullable=False),
        # salary, dividend, interest, rental (Phase 4), other
        
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('amount_monthly', sa.Numeric(15, 2), nullable=False),  # Trung bình/tháng
        sa.Column('is_active', sa.Boolean, default=True),
        
        sa.Column('metadata', sa.JSON, nullable=True),
        # For salary: {"company": "...", "frequency": "monthly"}
        # For dividend: {"asset_id": 123, "annual_yield": 0.06}
        
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
    )
    
    op.create_index('idx_income_user', 'income_streams', ['user_id', 'is_active'])
```

**Note:** Rental income chưa cover ở Phase 3A — đây chỉ là model đơn giản cho passive income awareness. Phase 4 sẽ có rental logic đầy đủ với tenant tracking, maintenance costs.

### Migration 4: Update Users table

```python
# alembic/versions/xxx_add_user_wealth_fields.py

def upgrade():
    op.add_column('users', sa.Column('primary_currency', sa.String(3), default='VND'))
    op.add_column('users', sa.Column('wealth_level', sa.String(20), nullable=True))
    # Values: starter, young_prof, mass_affluent, hnw
    op.add_column('users', sa.Column('expense_threshold_micro', sa.Integer, default=200000))
    op.add_column('users', sa.Column('expense_threshold_major', sa.Integer, default=2000000))
    op.add_column('users', sa.Column('briefing_enabled', sa.Boolean, default=True))
    op.add_column('users', sa.Column('briefing_time', sa.Time, default='07:00:00'))
```

---

## 1.2 — Asset Type Definitions

### File: `content/asset_categories.yaml`

```yaml
# Định nghĩa các loại asset và metadata schema

asset_types:
  cash:
    icon: "💵"
    label_vi: "Tiền mặt & Tài khoản"
    subtypes:
      - bank_savings: "Tiết kiệm ngân hàng"
      - bank_checking: "Tài khoản thanh toán"
      - cash: "Tiền mặt"
      - e_wallet: "Ví điện tử (MoMo, ZaloPay)"
    required_fields: [initial_value, name]
    optional_fields: [bank_name, interest_rate]
    
  stock:
    icon: "📈"
    label_vi: "Chứng khoán"
    subtypes:
      - vn_stock: "Cổ phiếu VN (HOSE/HNX)"
      - fund: "Quỹ mở (VCBF, Dragon Capital...)"
      - etf: "ETF (E1VFVN30...)"
      - foreign_stock: "Cổ phiếu nước ngoài"
    required_fields: [ticker, quantity, initial_value]
    optional_fields: [broker]
    
  real_estate:
    icon: "🏠"
    label_vi: "Bất động sản"
    subtypes:
      - house_primary: "Nhà ở (Case A - không sinh lợi)"
      - land: "Đất (Case C - đầu tư)"
      - # Note: rental property (Case B) sẽ được add ở Phase 4
    required_fields: [name, address, initial_value, current_value]
    optional_fields: [area_sqm, year_built]
    
  crypto:
    icon: "₿"
    label_vi: "Tiền số"
    subtypes:
      - bitcoin: "BTC"
      - ethereum: "ETH"
      - stablecoin: "USDT/USDC"
      - altcoin: "Coin khác"
    required_fields: [symbol, quantity]
    optional_fields: [wallet, exchange]
    
  gold:
    icon: "🥇"
    label_vi: "Vàng"
    subtypes:
      - sjc: "Vàng SJC"
      - pnj: "Vàng PNJ"
      - nhẫn: "Vàng nhẫn"
      - trang_suc: "Trang sức"
    required_fields: [weight_gram, initial_value]
    optional_fields: [purity]
    
  other:
    icon: "📦"
    label_vi: "Khác"
    subtypes:
      - vehicle: "Xe cộ"
      - collection: "Đồ sưu tầm"
      - business: "Kinh doanh"
      - other: "Khác"
    required_fields: [name, initial_value]
```

### File: `app/wealth/models/asset_types.py`

```python
"""
Asset type enum và metadata schemas.
"""

from enum import Enum
import yaml
from pathlib import Path


class AssetType(str, Enum):
    CASH = "cash"
    STOCK = "stock"
    REAL_ESTATE = "real_estate"
    CRYPTO = "crypto"
    GOLD = "gold"
    OTHER = "other"


def load_asset_categories():
    path = Path("content/asset_categories.yaml")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


ASSET_CATEGORIES = load_asset_categories()


def get_asset_config(asset_type: str) -> dict:
    """Get full config cho 1 asset type."""
    return ASSET_CATEGORIES["asset_types"].get(asset_type, {})


def get_subtypes(asset_type: str) -> dict:
    """Get subtypes cho 1 asset type."""
    config = get_asset_config(asset_type)
    return config.get("subtypes", {})
```

---

## 1.3 — Asset Service

### File: `app/wealth/services/asset_service.py`

```python
"""
Core asset service - CRUD operations cho assets.
"""

from datetime import datetime, date
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.wealth.models.asset import Asset
from app.wealth.models.asset_snapshot import AssetSnapshot
from app.database import get_session


class AssetService:
    async def create_asset(
        self,
        user_id: int,
        asset_type: str,
        name: str,
        initial_value: Decimal,
        current_value: Decimal = None,
        acquired_at: date = None,
        subtype: str = None,
        metadata: dict = None,
        description: str = None,
    ) -> Asset:
        """Create new asset và tạo snapshot đầu tiên."""
        async with get_session() as session:
            asset = Asset(
                user_id=user_id,
                asset_type=asset_type,
                subtype=subtype,
                name=name,
                initial_value=initial_value,
                current_value=current_value or initial_value,
                acquired_at=acquired_at or date.today(),
                metadata=metadata or {},
                description=description,
                last_valued_at=datetime.utcnow(),
            )
            session.add(asset)
            await session.flush()  # Get asset.id
            
            # Tạo snapshot đầu tiên
            snapshot = AssetSnapshot(
                asset_id=asset.id,
                user_id=user_id,
                snapshot_date=date.today(),
                value=asset.current_value,
                source="user_input",
            )
            session.add(snapshot)
            
            await session.commit()
            return asset
    
    async def update_current_value(
        self,
        asset_id: int,
        user_id: int,
        new_value: Decimal,
        source: str = "user_input",
    ):
        """Update giá trị hiện tại, tạo snapshot."""
        async with get_session() as session:
            asset = await session.get(Asset, asset_id)
            if not asset or asset.user_id != user_id:
                raise ValueError("Asset not found or not owned by user")
            
            asset.current_value = new_value
            asset.last_valued_at = datetime.utcnow()
            
            # Tạo/update snapshot hôm nay
            existing = await session.execute(
                select(AssetSnapshot).where(
                    AssetSnapshot.asset_id == asset_id,
                    AssetSnapshot.snapshot_date == date.today(),
                )
            )
            snapshot = existing.scalar_one_or_none()
            
            if snapshot:
                snapshot.value = new_value
                snapshot.source = source
            else:
                snapshot = AssetSnapshot(
                    asset_id=asset_id,
                    user_id=user_id,
                    snapshot_date=date.today(),
                    value=new_value,
                    source=source,
                )
                session.add(snapshot)
            
            await session.commit()
    
    async def get_user_assets(
        self,
        user_id: int,
        include_inactive: bool = False,
    ) -> list[Asset]:
        async with get_session() as session:
            query = select(Asset).where(Asset.user_id == user_id)
            if not include_inactive:
                query = query.where(Asset.is_active == True)
            
            result = await session.execute(query)
            return result.scalars().all()
    
    async def soft_delete(self, asset_id: int, user_id: int, sold_value: Decimal = None):
        """Đánh dấu sold, không xóa."""
        async with get_session() as session:
            asset = await session.get(Asset, asset_id)
            if not asset or asset.user_id != user_id:
                raise ValueError("Asset not found")
            
            asset.is_active = False
            asset.sold_at = date.today()
            asset.sold_value = sold_value
            await session.commit()
```

---

## 1.4 — Net Worth Calculator

### File: `app/wealth/services/net_worth_calculator.py`

```python
"""
Tính net worth — core logic của product.
"""

from decimal import Decimal
from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass
class NetWorthBreakdown:
    total: Decimal
    by_type: dict  # {"cash": 500_000_000, "stock": ...}
    asset_count: int
    largest_asset: tuple  # (name, value)
    currency: str = "VND"


@dataclass
class NetWorthChange:
    current: Decimal
    previous: Decimal
    change_absolute: Decimal
    change_percentage: float
    period_label: str  # "hôm qua", "tuần trước", "tháng trước"


class NetWorthCalculator:
    def __init__(self, asset_service):
        self.asset_service = asset_service
    
    async def calculate(self, user_id: int) -> NetWorthBreakdown:
        """Tính net worth hiện tại."""
        assets = await self.asset_service.get_user_assets(user_id)
        
        by_type = {}
        total = Decimal(0)
        largest = (None, Decimal(0))
        
        for asset in assets:
            value = asset.current_value
            total += value
            
            if asset.asset_type not in by_type:
                by_type[asset.asset_type] = Decimal(0)
            by_type[asset.asset_type] += value
            
            if value > largest[1]:
                largest = (asset.name, value)
        
        return NetWorthBreakdown(
            total=total,
            by_type=by_type,
            asset_count=len(assets),
            largest_asset=largest,
        )
    
    async def calculate_historical(
        self,
        user_id: int,
        target_date: date,
    ) -> Decimal:
        """Tính net worth tại 1 ngày cụ thể (từ snapshots)."""
        async with get_session() as session:
            # Get latest snapshot ≤ target_date for each asset
            query = """
                SELECT DISTINCT ON (asset_id) value
                FROM asset_snapshots
                WHERE user_id = :user_id 
                  AND snapshot_date <= :date
                ORDER BY asset_id, snapshot_date DESC
            """
            result = await session.execute(
                query, {"user_id": user_id, "date": target_date}
            )
            values = [row[0] for row in result]
            return sum(values) or Decimal(0)
    
    async def calculate_change(
        self,
        user_id: int,
        period: str = "day",  # day, week, month, year
    ) -> NetWorthChange:
        """So sánh current với past."""
        current_breakdown = await self.calculate(user_id)
        current = current_breakdown.total
        
        past_date_map = {
            "day": date.today() - timedelta(days=1),
            "week": date.today() - timedelta(days=7),
            "month": date.today() - timedelta(days=30),
            "year": date.today() - timedelta(days=365),
        }
        
        past_date = past_date_map[period]
        previous = await self.calculate_historical(user_id, past_date)
        
        change = current - previous
        pct = float(change / previous * 100) if previous > 0 else 0
        
        labels = {
            "day": "hôm qua",
            "week": "tuần trước",
            "month": "tháng trước",
            "year": "năm trước",
        }
        
        return NetWorthChange(
            current=current,
            previous=previous,
            change_absolute=change,
            change_percentage=pct,
            period_label=labels[period],
        )
```

---

## 1.5 — Wealth Level Detection (Ladder)

### File: `app/wealth/ladder.py`

```python
"""
Detect user's wealth level để adapt UI và messaging.
"""

from decimal import Decimal
from enum import Enum


class WealthLevel(str, Enum):
    STARTER = "starter"              # 0 - 30tr
    YOUNG_PROFESSIONAL = "young_prof"  # 30tr - 200tr
    MASS_AFFLUENT = "mass_affluent"    # 200tr - 1 tỷ
    HIGH_NET_WORTH = "hnw"             # 1 tỷ+


def detect_level(net_worth: Decimal) -> WealthLevel:
    """Detect level từ net worth."""
    if net_worth < Decimal("30_000_000"):
        return WealthLevel.STARTER
    elif net_worth < Decimal("200_000_000"):
        return WealthLevel.YOUNG_PROFESSIONAL
    elif net_worth < Decimal("1_000_000_000"):
        return WealthLevel.MASS_AFFLUENT
    else:
        return WealthLevel.HIGH_NET_WORTH


def next_milestone(net_worth: Decimal) -> tuple[Decimal, WealthLevel]:
    """Mức tiếp theo user cần đạt."""
    if net_worth < Decimal("30_000_000"):
        return Decimal("30_000_000"), WealthLevel.YOUNG_PROFESSIONAL
    elif net_worth < Decimal("100_000_000"):
        return Decimal("100_000_000"), WealthLevel.YOUNG_PROFESSIONAL
    elif net_worth < Decimal("200_000_000"):
        return Decimal("200_000_000"), WealthLevel.MASS_AFFLUENT
    elif net_worth < Decimal("500_000_000"):
        return Decimal("500_000_000"), WealthLevel.MASS_AFFLUENT
    elif net_worth < Decimal("1_000_000_000"):
        return Decimal("1_000_000_000"), WealthLevel.HIGH_NET_WORTH
    else:
        # HNW: milestones theo ty
        current_ty = int(net_worth / Decimal("1_000_000_000"))
        next_ty = current_ty + 1
        return Decimal(next_ty * 1_000_000_000), WealthLevel.HIGH_NET_WORTH
```

---

## 1.6 — Asset Entry Flow (Onboarding Assets)

### File: `app/bot/handlers/asset_entry.py`

Đây là **critical UX** — nếu user fail ở bước này, họ bỏ app.

```python
"""
Flow nhập asset lần đầu.
Thiết kế: TỐI THIỂU questions, MAXIMUM tự động.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from app.wealth.models.asset_types import AssetType, ASSET_CATEGORIES


async def start_asset_entry_wizard(update: Update, context):
    """Entry point - user tap 'Thêm tài sản'."""
    text = """💎 Thêm tài sản mới

Loại tài sản nào bạn muốn thêm?"""
    
    keyboard = [
        [
            InlineKeyboardButton("💵 Tiền mặt / TK", callback_data="asset_add:cash"),
            InlineKeyboardButton("📈 Chứng khoán", callback_data="asset_add:stock"),
        ],
        [
            InlineKeyboardButton("🏠 Bất động sản", callback_data="asset_add:real_estate"),
            InlineKeyboardButton("₿ Crypto", callback_data="asset_add:crypto"),
        ],
        [
            InlineKeyboardButton("🥇 Vàng", callback_data="asset_add:gold"),
            InlineKeyboardButton("📦 Khác", callback_data="asset_add:other"),
        ],
    ]
    
    await update.effective_message.reply_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_asset_type_selected(update, context):
    """User chọn loại asset → bắt đầu wizard từng loại."""
    query = update.callback_query
    _, asset_type = query.data.split(":")
    
    # Route tới wizard tương ứng
    wizards = {
        "cash": start_cash_wizard,
        "stock": start_stock_wizard,
        "real_estate": start_real_estate_wizard,
        "crypto": start_crypto_wizard,
        "gold": start_gold_wizard,
        "other": start_other_wizard,
    }
    
    await wizards[asset_type](update, context)


# ===========================================
# CASH WIZARD — Simple nhất
# ===========================================

async def start_cash_wizard(update, context):
    """
    Cash chỉ cần: tên + số tiền.
    2 câu hỏi total.
    """
    context.user_data["asset_draft"] = {"asset_type": "cash"}
    
    # Ask subtype
    text = "💵 Tiền ở đâu?"
    keyboard = [
        [InlineKeyboardButton("🏦 Tiết kiệm ngân hàng", callback_data="cash_subtype:bank_savings")],
        [InlineKeyboardButton("💳 Tài khoản thanh toán", callback_data="cash_subtype:bank_checking")],
        [InlineKeyboardButton("💵 Tiền mặt", callback_data="cash_subtype:cash")],
        [InlineKeyboardButton("📱 Ví điện tử", callback_data="cash_subtype:e_wallet")],
    ]
    
    await update.effective_message.reply_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_cash_subtype(update, context):
    query = update.callback_query
    _, subtype = query.data.split(":")
    
    context.user_data["asset_draft"]["subtype"] = subtype
    context.user_data["asset_draft_step"] = "cash_amount"
    
    # Ask tên + số tiền in 1 message
    labels = {
        "bank_savings": "Tên ngân hàng + số tiền",
        "bank_checking": "Tên ngân hàng + số dư",
        "cash": "Số tiền mặt có",
        "e_wallet": "Ví nào + số dư",
    }
    
    examples = {
        "bank_savings": "Ví dụ: 'VCB 100 triệu' hoặc 'Techcom 50tr'",
        "bank_checking": "Ví dụ: 'MB 15tr'",
        "cash": "Ví dụ: '5 triệu'",
        "e_wallet": "Ví dụ: 'MoMo 2tr' hoặc 'ZaloPay 500k'",
    }
    
    text = f"💬 {labels[subtype]}\n\n{examples[subtype]}"
    await query.message.reply_text(text)


async def handle_cash_text_input(update, context):
    """
    Parse câu dạng "VCB 100 triệu" → name=VCB, amount=100tr.
    Dùng LLM cho flexibility.
    """
    if context.user_data.get("asset_draft_step") != "cash_amount":
        return False  # Not for this handler
    
    text = update.message.text
    
    # Parse với LLM hoặc rule-based đơn giản
    parsed = await parse_cash_input(text)
    
    if not parsed:
        await update.message.reply_text(
            "Mình chưa hiểu lắm 😅 Bạn thử lại theo format 'Tên + số tiền' nhé?\n"
            "Ví dụ: 'VCB 100 triệu'"
        )
        return True
    
    # Save asset
    from app.wealth.services.asset_service import AssetService
    asset_service = AssetService()
    
    draft = context.user_data["asset_draft"]
    asset = await asset_service.create_asset(
        user_id=update.effective_user.id,
        asset_type=draft["asset_type"],
        subtype=draft["subtype"],
        name=parsed["name"],
        initial_value=parsed["amount"],
        metadata={},
    )
    
    # Clear draft
    context.user_data.pop("asset_draft", None)
    context.user_data.pop("asset_draft_step", None)
    
    # Confirm + show updated net worth
    from app.bot.formatters.wealth_formatter import format_asset_added
    message = await format_asset_added(asset, user_id=update.effective_user.id)
    
    await update.message.reply_text(message)
    
    # Offer add more
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("➕ Thêm tài sản khác", callback_data="asset_add:start"),
        InlineKeyboardButton("✅ Xong rồi", callback_data="asset_add:done"),
    ]])
    
    await update.message.reply_text(
        "Tiếp tục thêm tài sản, hay xong rồi?",
        reply_markup=keyboard,
    )
    
    return True


async def parse_cash_input(text: str) -> dict | None:
    """
    Parse "VCB 100 triệu" → {"name": "VCB", "amount": 100_000_000}.
    """
    from app.capture.voice.nlu_parser import parse_transaction_text
    
    # Reuse amount parser từ Phase 3 cũ
    result = parse_transaction_text(text)
    if not result:
        return None
    
    return {
        "name": result.merchant.strip() or "Tài khoản",
        "amount": result.amount,
    }


# ===========================================
# STOCK WIZARD
# ===========================================

async def start_stock_wizard(update, context):
    """
    Stock cần nhiều info hơn: ticker, số lượng, giá mua TB.
    """
    context.user_data["asset_draft"] = {"asset_type": "stock"}
    context.user_data["asset_draft_step"] = "stock_ticker"
    
    text = """📈 Cổ phiếu / Quỹ mới

Mã cổ phiếu (ticker) là gì?

Ví dụ: VNM, VIC, HPG, E1VFVN30"""
    
    await update.effective_message.reply_text(text)


async def handle_stock_ticker(update, context):
    if context.user_data.get("asset_draft_step") != "stock_ticker":
        return False
    
    ticker = update.message.text.strip().upper()
    context.user_data["asset_draft"]["metadata"] = {"ticker": ticker}
    context.user_data["asset_draft_step"] = "stock_quantity"
    
    await update.message.reply_text(
        f"✅ {ticker}\n\n"
        "Bạn đang sở hữu bao nhiêu cổ phiếu?"
    )
    return True


async def handle_stock_quantity(update, context):
    if context.user_data.get("asset_draft_step") != "stock_quantity":
        return False
    
    try:
        quantity = int(update.message.text.strip().replace(",", "").replace(".", ""))
    except ValueError:
        await update.message.reply_text("Nhập số thôi nhé, ví dụ: 100")
        return True
    
    context.user_data["asset_draft"]["metadata"]["quantity"] = quantity
    context.user_data["asset_draft_step"] = "stock_price"
    
    await update.message.reply_text(
        f"✅ {quantity} cổ phiếu\n\n"
        "Giá mua trung bình mỗi cổ phiếu?\n"
        "(Ví dụ: '45000' hoặc '45k')"
    )
    return True


async def handle_stock_price(update, context):
    if context.user_data.get("asset_draft_step") != "stock_price":
        return False
    
    from app.capture.voice.nlu_parser import parse_transaction_text
    
    # Parse price
    text = update.message.text
    parsed = parse_transaction_text(text) or parse_number_flexible(text)
    
    if not parsed:
        await update.message.reply_text("Nhập giá giúp mình nhé, ví dụ '45k' hoặc '45000'")
        return True
    
    price = parsed.amount if hasattr(parsed, 'amount') else parsed
    
    draft = context.user_data["asset_draft"]
    draft["metadata"]["avg_price"] = price
    quantity = draft["metadata"]["quantity"]
    total_value = price * quantity
    
    # Ask for current price or use same
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"Dùng {price:,.0f}đ (giá mua)", callback_data="stock_price:same"),
        InlineKeyboardButton("Nhập giá hiện tại", callback_data="stock_price:new"),
    ]])
    
    await update.message.reply_text(
        f"✅ Giá mua TB: {price:,.0f}đ/cp\n"
        f"Tổng vốn: {total_value:,.0f}đ\n\n"
        "Giá hiện tại của cổ phiếu?",
        reply_markup=keyboard,
    )
    return True


# (Tương tự cho real_estate, crypto, gold wizards...)
```

**Critical UX principles đã áp dụng:**
- Cash wizard: **2 câu hỏi** xong (subtype + amount)
- Stock wizard: **3-4 câu hỏi** xong (ticker, quantity, avg price, current price)
- Dùng buttons mọi khi có thể, text input chỉ khi cần
- Parse flexible với LLM (VCB 100 triệu, 100tr, 100000000 đều ok)
- Sau mỗi step, show progress ("✅ VCB")

---

## 1.7 — Onboarding First Asset

Thêm vào Phase 2's onboarding flow:

```python
# app/bot/handlers/onboarding.py (extend)

async def step_6_first_asset(update, user):
    """
    Bước mới sau aha_moment của Phase 2.
    "Giờ hãy thêm tài sản đầu tiên"
    """
    text = f"""💎 Bước quan trọng cuối cùng {user.display_name}!

Hãy thêm ít nhất 1 tài sản của bạn.
Không cần đầy đủ, chỉ cần 1 thứ thôi.

Đơn giản nhất là tiền trong ngân hàng —
bao nhiêu trong TK cũng được.

Sẵn sàng chưa?"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 Tiền trong NH (5 giây)", callback_data="onboard_asset:cash")],
        [InlineKeyboardButton("📈 Tôi có đầu tư", callback_data="onboard_asset:invest")],
        [InlineKeyboardButton("🏠 Tôi có BĐS", callback_data="onboard_asset:real_estate")],
        [InlineKeyboardButton("⏭ Skip, thêm sau", callback_data="onboard_asset:skip")],
    ])
    
    await update.effective_message.reply_text(text, reply_markup=keyboard)
```

**Critical insight:** Cho user **skip option** — nếu họ ngại nhập, đừng ép. Wrap-up sau này sẽ nhắc lại.

---

## ✅ Checklist Cuối Tuần 1

- [ ] 4 migrations apply thành công
- [ ] `Asset` model với JSON metadata hoạt động
- [ ] `AssetSnapshot` table tạo snapshot tự động khi create/update
- [ ] `asset_categories.yaml` đầy đủ 6 loại
- [ ] `AssetService.create_asset()` tested
- [ ] `NetWorthCalculator.calculate()` accurate
- [ ] `NetWorthCalculator.calculate_change()` cho day/week/month/year
- [ ] `WealthLevel` detection đúng
- [ ] Asset entry wizard cho ít nhất 3 loại: cash, stock, real_estate
- [ ] Onboarding flow có step "first asset"
- [ ] Tự test: tạo 5 assets đa loại, net worth tính đúng

---

# 🌅 TUẦN 2: Morning Briefing Infrastructure

> **Quan trọng:** Morning Briefing là **retention driver #1** của Phase 3A. Đầu tư thời gian vào trải nghiệm này đáng giá hơn bất cứ feature nào.

## 2.1 — Briefing Templates (Ladder-aware)

### File: `content/briefing_templates.yaml`

```yaml
# Templates adapt theo wealth level của user
# Placeholder: {name}, {net_worth}, {change}, {pct}, etc.

starter:
  # User 0-30tr
  greeting:
    - "☀️ Chào buổi sáng {name}!"
    - "🌅 Chào {name}, một ngày mới!"
  
  net_worth_display:
    template: |
      💎 Tài sản hôm nay: {net_worth}
      {change_emoji} {change_relative_str}
    no_change: |
      💎 Tài sản hôm nay: {net_worth}
      (Chưa thay đổi so với hôm qua)
  
  progress_context:
    template: |
      🎯 Mục tiêu tiếp: {next_milestone}
      Còn {remaining} nữa — với tốc độ hiện tại,
      đạt vào {eta_date}.
  
  educational_tips:
    - |
      💡 Tip hôm nay: Lãi kép là "kỳ diệu thứ 8 của thế giới" (Einstein).
      100k tiết kiệm hôm nay với lãi 6%/năm
      = 180k sau 10 năm. Ngồi không thôi!
    - |
      💡 3 khoản khẩn cấp mỗi người nên có:
      1. Quỹ khẩn cấp (3-6 tháng chi tiêu)
      2. Bảo hiểm y tế
      3. Tiết kiệm dài hạn

young_prof:
  # 30tr - 200tr  
  greeting:
    - "☀️ Chào {name}! Thị trường hôm nay..."
    - "🌅 Chào buổi sáng {name}!"
  
  net_worth_display:
    template: |
      💎 Net worth: {net_worth}
      {change_emoji} {change} ({pct}%) so với {period}
      
      📊 Phân bổ:
      {breakdown_lines}
  
  action_prompts:
    - |
      💡 Tuần này bạn dư {excess_cash}.
      Đề xuất: chuyển vào quỹ VFMVN30 để
      bắt đầu danh mục đầu tư?
      
      [Tìm hiểu] [Bắt đầu đầu tư]

mass_affluent:
  # 200tr - 1 tỷ
  greeting:
    - "☀️ Chào anh/chị {name}!"
  
  net_worth_display:
    template: |
      💎 Giá trị ròng: {net_worth}
      {change_emoji} {change} so với {period}
      
      📊 Phân bổ tài sản:
      {breakdown_lines}
      
      💰 Dòng tiền tháng này:
      Thu: {income_ytd}  Chi: {expense_ytd}
      Ròng: {net_cashflow}
      Tỷ lệ tiết kiệm: {saving_rate}% {saving_emoji}
  
  market_intelligence:
    # (Phase 3B sẽ fill data)
    template: |
      📰 Tin đáng chú ý hôm nay:
      {market_news}
      
      🎯 Ảnh hưởng tới danh mục anh/chị:
      {portfolio_impact}

hnw:
  # 1 tỷ+
  # Full CFO experience
  greeting:
    - "☀️ Good morning anh/chị {name}!"
  
  net_worth_display:
    template: |
      💎 Tổng giá trị ròng: {net_worth_formatted}
      {change_emoji} Biến động: {change} ({pct}%) {period}
      
      Phân bổ:
      {detailed_breakdown}
      
      📈 Performance metrics:
      • YTD return: {ytd_return}%
      • Volatility: {volatility}
      • Diversification: {div_score}/10

# ===================
# Common messages (not ladder-specific)
# ===================

spending_reminder:
  # Gửi kèm briefing nếu hôm qua chi nhiều
  high_spend_yesterday: |
    💸 Hôm qua chi tiêu: {yesterday_total} 
    ({pct}% cao hơn trung bình)
    
    Tap [Xem chi tiết] nếu muốn review.

storytelling_prompt:
  # Gắn cuối mỗi briefing
  - |
    💭 Hôm qua anh/chị có chi gì đáng kể không?
    (Chi nhỏ dưới {threshold} không cần, mình lo)
    
    [Kể nhanh] [Không có gì]
  - |
    💭 Hôm qua có chi gì >{threshold} không?
    Kể mình nghe để tổng hợp nhé!
```

---

## 2.2 — Briefing Formatter

### File: `app/bot/formatters/briefing_formatter.py`

```python
"""
Format morning briefing based on user level.
"""

import random
import yaml
from decimal import Decimal
from pathlib import Path

from app.wealth.ladder import WealthLevel, detect_level, next_milestone
from app.wealth.services.net_worth_calculator import NetWorthCalculator
from app.bot.formatters.money import format_money_short, format_money_full


class BriefingFormatter:
    def __init__(self):
        self._templates = self._load_templates()
    
    def _load_templates(self):
        path = Path("content/briefing_templates.yaml")
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    async def generate_for_user(self, user) -> str:
        """Generate personalized morning briefing."""
        # 1. Calculate metrics
        calculator = NetWorthCalculator()
        current = await calculator.calculate(user.id)
        level = detect_level(current.total)
        
        # Change vs yesterday
        change = await calculator.calculate_change(user.id, period="day")
        
        # 2. Build message pieces
        level_templates = self._templates[level.value]
        
        greeting = random.choice(level_templates["greeting"]).format(
            name=user.display_name or "bạn"
        )
        
        net_worth_section = self._format_net_worth(
            level_templates, current, change
        )
        
        # 3. Level-specific content
        if level == WealthLevel.STARTER:
            milestone_section = await self._format_milestone_progress(user, current, level)
            tip = random.choice(level_templates["educational_tips"])
            body = f"{net_worth_section}\n\n{milestone_section}\n\n{tip}"
        
        elif level == WealthLevel.YOUNG_PROFESSIONAL:
            # Check for opportunities
            action = await self._maybe_action_prompt(user, current, level_templates)
            body = f"{net_worth_section}\n\n{action}" if action else net_worth_section
        
        elif level == WealthLevel.MASS_AFFLUENT:
            # Add cashflow
            cashflow_section = await self._format_cashflow(user)
            # Market intel (Phase 3B sẽ implement thật)
            market_section = "📰 (Market intelligence sắp có trong Phase 3B)"
            body = f"{net_worth_section}\n\n{cashflow_section}\n\n{market_section}"
        
        else:  # HNW
            # Full CFO
            body = await self._format_hnw_briefing(user, current)
        
        # 4. Append storytelling prompt
        storytelling = self._format_storytelling_prompt(user)
        
        # 5. Combine
        return f"{greeting}\n\n{body}\n\n{storytelling}"
    
    def _format_net_worth(self, templates, current, change):
        """Format section giá trị ròng."""
        template_config = templates["net_worth_display"]
        
        if change.change_absolute == 0:
            return template_config["no_change"].format(
                net_worth=format_money_full(current.total),
            )
        
        emoji = "📈" if change.change_absolute > 0 else "📉"
        sign = "+" if change.change_absolute > 0 else ""
        
        return template_config["template"].format(
            net_worth=format_money_full(current.total),
            change=f"{sign}{format_money_full(change.change_absolute)}",
            change_emoji=emoji,
            change_relative_str=f"{emoji} {sign}{format_money_short(change.change_absolute)} ({change.change_percentage:+.1f}%)",
            pct=f"{change.change_percentage:+.1f}",
            period=change.period_label,
            breakdown_lines=self._format_breakdown(current.by_type),
        )
    
    def _format_breakdown(self, by_type: dict) -> str:
        """Format asset type breakdown lines."""
        from app.wealth.models.asset_types import ASSET_CATEGORIES
        
        total = sum(by_type.values())
        if total == 0:
            return ""
        
        lines = []
        # Sort desc
        sorted_items = sorted(by_type.items(), key=lambda x: x[1], reverse=True)
        for asset_type, value in sorted_items:
            config = ASSET_CATEGORIES["asset_types"].get(asset_type, {})
            icon = config.get("icon", "📌")
            label = config.get("label_vi", asset_type)
            pct = value / total * 100
            
            lines.append(f"{icon} {label:<20} {format_money_short(value):>8} ({pct:.0f}%)")
        
        return "\n".join(lines)
    
    async def _format_milestone_progress(self, user, current, level):
        """For starter level — show next milestone."""
        next_target, next_level = next_milestone(current.total)
        remaining = next_target - current.total
        
        # Estimate ETA (rough: based on avg monthly saving)
        # For MVP: assume 10% of income per month
        # TODO: use actual data in Phase 4
        avg_monthly_saving = Decimal("3_000_000")  # Placeholder
        months_to_go = remaining / avg_monthly_saving if avg_monthly_saving > 0 else 999
        
        from datetime import date, timedelta
        eta = date.today() + timedelta(days=int(months_to_go * 30))
        
        level_templates = self._templates[level.value]
        template = level_templates["progress_context"]["template"]
        
        return template.format(
            next_milestone=format_money_full(next_target),
            remaining=format_money_full(remaining),
            eta_date=eta.strftime("%m/%Y"),
        )
    
    def _format_storytelling_prompt(self, user):
        """Gắn storytelling prompt cuối briefing."""
        threshold = format_money_short(user.expense_threshold_micro)
        template = random.choice(self._templates["storytelling_prompt"])
        return template.format(threshold=threshold)
    
    # ... similar methods for other sections
```

---

## 2.3 — Morning Briefing Job

### File: `app/scheduled/morning_briefing_job.py`

```python
"""
Scheduled job gửi morning briefing.
Chạy mỗi 15 phút để handle multiple time zones + adaptive timing.
"""

import asyncio
from datetime import datetime, time, timedelta

from app.services.user_service import UserService
from app.bot.formatters.briefing_formatter import BriefingFormatter
from app.bot.keyboards.briefing_keyboard import briefing_actions_keyboard
from app.bot.bot_instance import bot


async def run_morning_briefing_job():
    """
    Chạy mỗi 15 phút.
    Check user nào có briefing_time trong 15 phút tới → gửi.
    """
    user_service = UserService()
    formatter = BriefingFormatter()
    
    # Get users với briefing enabled, active trong 30 ngày
    users = await user_service.get_active_users(days=30, briefing_enabled=True)
    
    now = datetime.now().time()
    
    for user in users:
        target_time = user.briefing_time or time(7, 0)
        
        # Check nếu trong cửa sổ 15 phút tới target_time
        if not _is_within_15_min(now, target_time):
            continue
        
        # Check nếu hôm nay đã gửi chưa
        if await _already_sent_today(user.id, "morning_briefing"):
            continue
        
        try:
            # Generate briefing
            message = await formatter.generate_for_user(user)
            keyboard = briefing_actions_keyboard()
            
            # Send
            await bot.send_message(
                chat_id=user.telegram_id,
                text=message,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
            
            # Mark sent
            await _mark_sent(user.id, "morning_briefing")
            
            # Track
            from app.analytics import track, Event
            await track(Event(
                user_id=user.id,
                event_type="morning_briefing_sent",
                properties={"level": user.wealth_level},
                timestamp=datetime.utcnow(),
            ))
            
            # Rate limit
            await asyncio.sleep(1)
        
        except Exception as e:
            print(f"Briefing error for user {user.id}: {e}")


def _is_within_15_min(current: time, target: time) -> bool:
    """Check current trong cửa sổ [target, target+15min]."""
    current_min = current.hour * 60 + current.minute
    target_min = target.hour * 60 + target.minute
    return 0 <= (current_min - target_min) < 15
```

### File: `app/bot/keyboards/briefing_keyboard.py`

```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def briefing_actions_keyboard() -> InlineKeyboardMarkup:
    """Buttons đi kèm morning briefing."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Xem dashboard", callback_data="briefing:dashboard"),
            InlineKeyboardButton("💬 Kể chuyện", callback_data="briefing:story"),
        ],
        [
            InlineKeyboardButton("➕ Thêm tài sản", callback_data="asset_add:start"),
            InlineKeyboardButton("⚙️ Điều chỉnh giờ", callback_data="briefing:settings"),
        ],
    ])
```

---

## 2.4 — Daily Snapshot Job

### File: `app/scheduled/daily_snapshot_job.py`

```python
"""
Chạy 23:59 mỗi ngày.
Tạo snapshot cho tất cả active assets.
"""

from datetime import date, datetime
from app.wealth.models.asset import Asset
from app.wealth.models.asset_snapshot import AssetSnapshot


async def create_daily_snapshots():
    """Snapshot value của mọi active asset."""
    async with get_session() as session:
        # Get all active assets
        result = await session.execute(
            select(Asset).where(Asset.is_active == True)
        )
        assets = result.scalars().all()
        
        today = date.today()
        count = 0
        
        for asset in assets:
            # Check existing snapshot today
            existing = await session.execute(
                select(AssetSnapshot).where(
                    AssetSnapshot.asset_id == asset.id,
                    AssetSnapshot.snapshot_date == today,
                )
            )
            if existing.scalar_one_or_none():
                continue  # Already has snapshot
            
            # Create snapshot
            snapshot = AssetSnapshot(
                asset_id=asset.id,
                user_id=asset.user_id,
                snapshot_date=today,
                value=asset.current_value,
                source="auto_daily",
            )
            session.add(snapshot)
            count += 1
        
        await session.commit()
        print(f"Created {count} daily snapshots")
```

---

## ✅ Checklist Cuối Tuần 2

- [ ] `briefing_templates.yaml` đầy đủ 4 levels (starter, young_prof, mass_affluent, hnw)
- [ ] `BriefingFormatter.generate_for_user()` hoạt động
- [ ] Briefing adapt đúng theo user level
- [ ] Morning briefing job chạy mỗi 15 phút
- [ ] User có thể customize briefing time
- [ ] Daily snapshot job chạy 23:59
- [ ] Briefing có inline buttons (dashboard, story, add asset)
- [ ] Track analytics: briefing_sent, briefing_opened
- [ ] Test với 4 fake users (mỗi level 1) — briefings đúng

---

# 💬 TUẦN 3: Simple Storytelling Expense (Threshold-Based)

## 3.1 — Threshold Philosophy

Khác với Phase 3 cũ (track mọi giao dịch), Phase 3A chỉ track giao dịch quan trọng:

- **<200k (Micro):** Không track. Gộp aggregate.
- **200k - 2tr (Medium):** Storytelling optional, user kể thì track.
- **>2tr (Major):** Luôn track, đôi khi proactive detect.

**Thresholds tự động adapt** theo thu nhập:

```python
# app/wealth/services/threshold_service.py

def compute_thresholds(monthly_income: Decimal) -> tuple[Decimal, Decimal]:
    """
    Return (micro_threshold, major_threshold).
    """
    if monthly_income < Decimal("15_000_000"):
        return (Decimal("100_000"), Decimal("1_000_000"))
    elif monthly_income < Decimal("30_000_000"):
        return (Decimal("200_000"), Decimal("2_000_000"))
    elif monthly_income < Decimal("60_000_000"):
        return (Decimal("300_000"), Decimal("3_000_000"))
    else:  # 60tr+
        return (Decimal("500_000"), Decimal("5_000_000"))
```

User có thể override trong settings.

---

## 3.2 — Storytelling Extraction Prompt

### File: `app/bot/personality/storytelling_prompt.py`

```python
"""
LLM prompt cho extraction giao dịch từ câu chuyện.
Simplified từ Phase 3 cũ.
"""


STORYTELLING_PROMPT = """Bạn là AI finance assistant. User vừa kể về chi tiêu của họ.

Nhiệm vụ: Extract MỌI giao dịch đáng kể (>{threshold} VND).

QUAN TRỌNG:
- CHỈ extract giao dịch >={threshold}. Giao dịch nhỏ hơn → BỎ QUA.
- Nếu user nói "ăn phở 50k" mà threshold là 200k → KHÔNG extract.
- Nếu không chắc số tiền, đừng đoán, bỏ qua hoặc hỏi lại.

CATEGORIES:
- food: nhà hàng, gọi đồ ăn lớn, event ăn uống
- transport: Grab nhiều chuyến, xăng, taxi đường xa
- housing: tiền nhà, sửa chữa, đồ dùng gia đình
- shopping: quần áo, đồ điện tử
- health: thuốc, bác sĩ, gym
- entertainment: giải trí, du lịch
- education: học phí, sách
- investment: mua thêm stock, crypto
- gift: quà tặng, mừng sự kiện
- other: không rõ

OUTPUT JSON:
{{
  "transactions": [
    {{
      "amount": 500000,
      "merchant": "Nhà hàng Ngon Hà Nội",
      "category": "food",
      "time_hint": "tối qua",
      "context": "đi ăn với bạn",
      "confidence": 0.9
    }}
  ],
  "needs_clarification": [
    {{"question": "Bạn mua quần áo bao nhiêu tổng?"}}
  ],
  "ignored_small": [
    {{"amount_mentioned": "50k", "reason": "dưới threshold"}}
  ]
}}

User threshold: {threshold} VND
Story:
{story}
"""


async def extract_transactions_from_story(
    story: str,
    user_id: int,
    threshold: int = 200_000,
) -> dict:
    """Call LLM với prompt above."""
    from openai import AsyncOpenAI
    from app.config import settings
    
    client = AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com/v1",
    )
    
    prompt = STORYTELLING_PROMPT.format(
        threshold=threshold,
        story=story,
    )
    
    response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        max_tokens=1500,
    )
    
    import json
    return json.loads(response.choices[0].message.content)
```

---

## 3.3 — Storytelling Handler

### File: `app/bot/handlers/storytelling.py`

```python
"""
Handle storytelling replies.
Flow:
1. User tap "Kể chuyện" từ briefing keyboard
2. Bot mở storytelling mode
3. User text/voice → LLM extract
4. Bot hiện list transactions để confirm
5. User confirm → lưu DB
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from app.bot.personality.storytelling_prompt import extract_transactions_from_story
from app.wealth.services.threshold_service import compute_thresholds


async def start_storytelling(update, context):
    """User tap 'Kể chuyện' button."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Enter storytelling mode
    context.user_data["storytelling_mode"] = True
    
    # Get user threshold
    from app.services.user_service import UserService
    user = await UserService().get_by_telegram_id(user_id)
    threshold = user.expense_threshold_micro or 200_000
    
    text = f"""💬 Kể mình nghe...

Hôm qua bạn có chi gì đáng kể không?
(Chi dưới {threshold:,}đ mình tự lo, không cần nói)

Ví dụ:
• "Tối qua ăn nhà hàng với bạn 800k"
• "Mua điện thoại 15tr"
• "Đi du lịch Đà Lạt hết 5tr"

Gõ hoặc gửi voice — cái nào tiện."""
    
    await query.message.reply_text(text)


async def handle_storytelling_input(update, context):
    """Handle text/voice khi user đang trong storytelling mode."""
    if not context.user_data.get("storytelling_mode"):
        return False
    
    user_id = update.effective_user.id
    
    # Get text (from text or voice transcript)
    if update.message.voice:
        from app.capture.voice.whisper_client import transcribe_vietnamese
        voice_file = await update.message.voice.get_file()
        audio = await voice_file.download_as_bytearray()
        story = await transcribe_vietnamese(bytes(audio))
        
        # Show transcript
        await update.message.reply_text(f"🎤 Mình nghe: *{story}*", parse_mode="Markdown")
    else:
        story = update.message.text
    
    # Processing message
    processing = await update.message.reply_text("🔍 Đang tìm giao dịch...")
    
    try:
        # Get threshold
        from app.services.user_service import UserService
        user = await UserService().get_by_telegram_id(user_id)
        threshold = user.expense_threshold_micro or 200_000
        
        # Extract
        result = await extract_transactions_from_story(story, user_id, threshold)
        
        # Exit mode
        context.user_data.pop("storytelling_mode", None)
        
        # Build response
        transactions = result.get("transactions", [])
        ignored = result.get("ignored_small", [])
        needs_clarification = result.get("needs_clarification", [])
        
        if not transactions:
            msg = "Mình không thấy giao dịch nào trên mức threshold cả 😊"
            if ignored:
                msg += f"\n\n({len(ignored)} khoản nhỏ đã bỏ qua)"
            await processing.edit_text(msg)
            return True
        
        # Show confirmation
        lines = ["🔍 Mình tìm được:", ""]
        for i, tx in enumerate(transactions, 1):
            from app.config.categories import get_category
            cat = get_category(tx["category"])
            lines.append(
                f"{i}. {cat.emoji} {tx['merchant']} — {tx['amount']:,}đ"
            )
        
        lines.append("")
        lines.append("Đúng hết không?")
        
        # Store in context để confirm
        context.user_data["pending_transactions"] = transactions
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Đúng hết", callback_data="story_confirm:all"),
                InlineKeyboardButton("✏️ Sửa", callback_data="story_confirm:edit"),
            ],
            [
                InlineKeyboardButton("❌ Bỏ hết", callback_data="story_confirm:cancel"),
            ],
        ])
        
        await processing.edit_text("\n".join(lines), reply_markup=keyboard)
    
    except Exception as e:
        print(f"Storytelling error: {e}")
        await processing.edit_text("Có lỗi xử lý 😔 Thử lại nhé?")
    
    return True


async def handle_story_confirm(update, context):
    """User tap 'Đúng hết' → save all."""
    query = update.callback_query
    await query.answer()
    
    _, action = query.data.split(":")
    
    if action == "all":
        transactions = context.user_data.get("pending_transactions", [])
        
        from app.services.transaction_service import TransactionService
        tx_service = TransactionService()
        
        saved_count = 0
        for tx in transactions:
            await tx_service.create_transaction(
                user_id=query.from_user.id,
                amount=tx["amount"],
                merchant=tx["merchant"],
                category_code=tx["category"],
                source="storytelling",
                verified_by_user=True,
                description=tx.get("context", ""),
            )
            saved_count += 1
        
        context.user_data.pop("pending_transactions", None)
        
        await query.edit_message_text(
            f"✅ Đã lưu {saved_count} giao dịch!\n\n"
            "Cảm ơn bạn kể chuyện 💚"
        )
    
    elif action == "cancel":
        context.user_data.pop("pending_transactions", None)
        await query.edit_message_text("❌ Đã bỏ qua. Không lưu gì cả.")
    
    # ... handle "edit" case
```

---

## ✅ Checklist Cuối Tuần 3

- [ ] `compute_thresholds()` adapt theo income
- [ ] User có thể edit threshold trong settings
- [ ] Storytelling LLM prompt tested với 20+ câu chuyện mẫu
- [ ] Extract accuracy >80% cho threshold-based
- [ ] Handler với voice + text input
- [ ] Confirmation UI với "Đúng hết / Sửa / Bỏ"
- [ ] Integration với briefing keyboard "💬 Kể chuyện"
- [ ] Transaction saved với source="storytelling"
- [ ] Cashflow categories tổng hợp được từ storytelling + micro aggregate

---

# 📊 TUẦN 4: Net Worth Visualization + Polish

## 4.1 — Mini App Dashboard

### File: `app/miniapp/templates/net_worth_dashboard.html`

Đây là màn hình "North Star" — cần đẹp và rich.

```html
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tài sản của tôi</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <link rel="stylesheet" href="/static/miniapp/css/wealth.css">
</head>
<body>
    <div id="app">
        <div id="loading" class="loading"><div class="spinner"></div></div>
        
        <div id="content" style="display: none;">
            <!-- Hero: Net Worth -->
            <div class="hero-card">
                <div class="hero-label">💎 Giá trị ròng</div>
                <div class="hero-amount" id="net-worth">—</div>
                <div class="hero-change">
                    <span id="change-icon">📈</span>
                    <span id="change-amount">—</span>
                    <span class="change-period">so với tháng trước</span>
                </div>
            </div>
            
            <!-- Breakdown Pie -->
            <div class="section">
                <h2>Phân bổ tài sản</h2>
                <div class="chart-container">
                    <canvas id="pie-chart"></canvas>
                </div>
                <div id="breakdown-list"></div>
            </div>
            
            <!-- Trend -->
            <div class="section">
                <h2>Xu hướng 90 ngày</h2>
                <div class="chart-container">
                    <canvas id="trend-chart"></canvas>
                </div>
                <div class="period-selector">
                    <button class="period-btn active" data-days="30">30 ngày</button>
                    <button class="period-btn" data-days="90">90 ngày</button>
                    <button class="period-btn" data-days="365">1 năm</button>
                </div>
            </div>
            
            <!-- Milestone Progress (starter level only) -->
            <div class="section" id="milestone-section" style="display:none;">
                <h2>🎯 Mục tiêu tiếp theo</h2>
                <div class="milestone-bar">
                    <div class="milestone-fill" id="milestone-fill"></div>
                </div>
                <div class="milestone-info">
                    <span id="milestone-current">—</span> /
                    <span id="milestone-target">—</span>
                </div>
            </div>
            
            <!-- Assets list -->
            <div class="section">
                <h2>📦 Tài sản của bạn</h2>
                <div id="assets-list"></div>
                <button class="add-btn" onclick="addAsset()">+ Thêm tài sản</button>
            </div>
        </div>
    </div>
    
    <script src="/static/miniapp/js/wealth_dashboard.js"></script>
</body>
</html>
```

### File: `app/miniapp/static/js/wealth_dashboard.js`

```javascript
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

let currentPeriodDays = 30;

function formatMoney(amount) {
    if (amount >= 1_000_000_000) {
        return (amount / 1_000_000_000).toFixed(2).replace(/\.?0+$/, '') + ' tỷ';
    }
    if (amount >= 1_000_000) {
        return (amount / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'tr';
    }
    if (amount >= 1000) {
        return Math.round(amount / 1000) + 'k';
    }
    return amount + 'đ';
}

function formatMoneyFull(amount) {
    return new Intl.NumberFormat('vi-VN').format(amount) + 'đ';
}

async function fetchAPI(endpoint) {
    const response = await fetch(`/miniapp/api${endpoint}`, {
        headers: { 'X-Telegram-Init-Data': tg.initData },
    });
    if (!response.ok) throw new Error('API error');
    return response.json();
}

async function loadDashboard() {
    try {
        const data = await fetchAPI('/wealth/overview');
        
        // Net worth hero
        document.getElementById('net-worth').textContent = formatMoneyFull(data.net_worth);
        
        // Change
        const change = data.change_month;
        const icon = change.change >= 0 ? '📈' : '📉';
        const sign = change.change >= 0 ? '+' : '';
        document.getElementById('change-icon').textContent = icon;
        document.getElementById('change-amount').textContent = 
            `${sign}${formatMoneyFull(Math.abs(change.change))} (${sign}${change.pct.toFixed(1)}%)`;
        
        // Pie chart
        renderPieChart(data.breakdown);
        renderBreakdownList(data.breakdown);
        
        // Trend chart
        renderTrendChart(data.trend_90d);
        
        // Milestone (if starter)
        if (data.level === 'starter' && data.next_milestone) {
            document.getElementById('milestone-section').style.display = 'block';
            renderMilestone(data.net_worth, data.next_milestone);
        }
        
        // Assets list
        renderAssetsList(data.assets);
        
        document.getElementById('loading').style.display = 'none';
        document.getElementById('content').style.display = 'block';
    } catch (error) {
        console.error(error);
        tg.showAlert('Lỗi tải dữ liệu');
    }
}

function renderPieChart(breakdown) {
    const ctx = document.getElementById('pie-chart').getContext('2d');
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: breakdown.map(b => b.label),
            datasets: [{
                data: breakdown.map(b => b.value),
                backgroundColor: breakdown.map(b => b.color),
                borderWidth: 2,
                borderColor: '#fff',
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.label}: ${formatMoney(ctx.parsed)}`,
                    },
                },
            },
        },
    });
}

function renderBreakdownList(breakdown) {
    const container = document.getElementById('breakdown-list');
    const total = breakdown.reduce((s, b) => s + b.value, 0);
    
    container.innerHTML = breakdown.map(b => `
        <div class="breakdown-row">
            <span class="breakdown-icon">${b.icon}</span>
            <span class="breakdown-label">${b.label}</span>
            <span class="breakdown-value">${formatMoney(b.value)}</span>
            <span class="breakdown-pct">${(b.value/total*100).toFixed(0)}%</span>
        </div>
    `).join('');
}

function renderTrendChart(trend) {
    const ctx = document.getElementById('trend-chart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: trend.map(t => t.date.slice(5)),  // MM-DD
            datasets: [{
                data: trend.map(t => t.value),
                borderColor: '#4ECDC4',
                backgroundColor: 'rgba(78, 205, 196, 0.1)',
                fill: true,
                tension: 0.3,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
            },
            scales: {
                y: {
                    ticks: { callback: v => formatMoney(v) },
                },
            },
        },
    });
}

function renderMilestone(current, target) {
    const pct = Math.min(100, (current / target.amount) * 100);
    document.getElementById('milestone-fill').style.width = `${pct}%`;
    document.getElementById('milestone-current').textContent = formatMoneyFull(current);
    document.getElementById('milestone-target').textContent = formatMoneyFull(target.amount);
}

function renderAssetsList(assets) {
    const container = document.getElementById('assets-list');
    container.innerHTML = assets.map(asset => `
        <div class="asset-card" onclick="viewAsset(${asset.id})">
            <div class="asset-icon">${asset.icon}</div>
            <div class="asset-info">
                <div class="asset-name">${asset.name}</div>
                <div class="asset-type">${asset.type_label}</div>
            </div>
            <div class="asset-value">
                <div class="asset-current">${formatMoney(asset.current_value)}</div>
                <div class="asset-change ${asset.change >= 0 ? 'positive' : 'negative'}">
                    ${asset.change >= 0 ? '+' : ''}${asset.change_pct.toFixed(1)}%
                </div>
            </div>
        </div>
    `).join('');
}

function addAsset() {
    tg.close();
    // Bot sẽ handle /add_asset command
}

// Period selector
document.querySelectorAll('.period-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
        document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentPeriodDays = parseInt(btn.dataset.days);
        
        const trend = await fetchAPI(`/wealth/trend?days=${currentPeriodDays}`);
        renderTrendChart(trend);
    });
});

loadDashboard();
```

### File: `app/miniapp/routes.py` (thêm endpoints)

```python
@router.get("/api/wealth/overview")
async def wealth_overview(auth = Depends(require_miniapp_auth)):
    user_id = auth["user_id"]
    
    from app.wealth.services.net_worth_calculator import NetWorthCalculator
    from app.wealth.services.asset_service import AssetService
    from app.wealth.ladder import detect_level, next_milestone
    
    calculator = NetWorthCalculator()
    asset_service = AssetService()
    
    current = await calculator.calculate(user_id)
    change_day = await calculator.calculate_change(user_id, "day")
    change_month = await calculator.calculate_change(user_id, "month")
    
    level = detect_level(current.total)
    
    # Get trend
    trend = await get_trend_data(user_id, days=90)
    
    # Assets list
    assets = await asset_service.get_user_assets(user_id)
    
    # Format breakdown
    from app.wealth.models.asset_types import ASSET_CATEGORIES
    breakdown = []
    for asset_type, value in current.by_type.items():
        config = ASSET_CATEGORIES["asset_types"].get(asset_type, {})
        breakdown.append({
            "asset_type": asset_type,
            "label": config.get("label_vi", asset_type),
            "icon": config.get("icon", "📌"),
            "value": float(value),
            "color": _color_for_type(asset_type),
        })
    breakdown.sort(key=lambda x: x["value"], reverse=True)
    
    result = {
        "net_worth": float(current.total),
        "level": level.value,
        "change_day": {
            "change": float(change_day.change_absolute),
            "pct": change_day.change_percentage,
        },
        "change_month": {
            "change": float(change_month.change_absolute),
            "pct": change_month.change_percentage,
        },
        "breakdown": breakdown,
        "trend_90d": trend,
        "assets": [_serialize_asset(a) for a in assets],
    }
    
    # Add milestone for starter
    if level.value == "starter":
        next_target, _ = next_milestone(current.total)
        result["next_milestone"] = {"amount": float(next_target)}
    
    return result
```

---

## 4.2 — User Testing Week

### Test Protocol

Chọn **7 users** đa dạng:

- 2 Level 0 (Starter): 22-25 tuổi, lương 10-20tr
- 3 Level 1 (Young Prof): 26-32 tuổi, lương 25-45tr  
- 2 Level 2 (Mass Affluent): 35-45 tuổi, có BĐS + stock

### Daily tasks (user nhận trước khi test):

**Ngày 1:** Onboard + nhập ít nhất 3 loại asset
**Ngày 2-6:** Nhận morning briefing lúc 7h, interact với buttons
**Ngày 7:** Full interview 30 phút

### Metrics to track:

```python
# Add to analytics

# Briefing engagement
await track(Event(event_type="morning_briefing_opened"))  # User tap button trong 30p sau receive
await track(Event(event_type="dashboard_viewed", properties={"from": "briefing"}))
await track(Event(event_type="storytelling_started"))
await track(Event(event_type="storytelling_completed"))

# Asset management
await track(Event(event_type="asset_added", properties={"type": "cash"}))
await track(Event(event_type="asset_value_updated"))
```

### Interview questions:

1. **Cảm xúc tổng thể:** Lần đầu thấy net worth hiển thị — cảm xúc đầu tiên là gì?
2. **Morning briefing:** Ngày nào bạn mở đọc nhất? Không mở? Tại sao?
3. **Storytelling:** Cảm thấy natural hay forced?
4. **Asset entry:** Bước nào khó nhất? Có bỏ cuộc không?
5. **Recommendation:** Ai bạn sẽ giới thiệu app này?
6. **Price:** Với feature này, bạn sẵn lòng trả bao nhiêu/tháng?

### Success criteria:

- **≥5/7 users** mở briefing ít nhất 5/7 ngày
- **≥4/7 users** add thêm asset sau ngày 1
- **≥3/7 users** tham gia storytelling ≥3 lần
- **≥5/7 users** nói sẵn lòng trả ≥100k/tháng

---

## ✅ Checklist Cuối Tuần 4 (Exit Criteria Phase 3A)

- [ ] Mini App dashboard load <2s
- [ ] Pie chart + Line chart render đẹp
- [ ] Trend period selector hoạt động (30/90/365)
- [ ] Milestone display cho starter level
- [ ] Assets list với edit actions
- [ ] 7 users test trong 1 tuần
- [ ] Metrics: ≥5/7 users open briefing ≥5 ngày
- [ ] Retention D7 ≥50%
- [ ] 0 critical bugs
- [ ] Ready to ship public beta

---

# 🚧 Bẫy Thường Gặp Phase 3A

## 1. Over-engineer asset data model
Tạo 6 tables riêng cho 6 loại asset → khó maintain. Dùng JSON metadata như thiết kế.

## 2. Push user add nhiều asset quá sớm
Onboarding chỉ hỏi 1 asset. Các asset khác, bot nhắc dần qua briefings.

## 3. Briefing quá dài
Màn hình điện thoại nhỏ. Briefing >1 screen → user skip. Test on actual phone.

## 4. LLM extraction sai
Storytelling fail → user mất trust. Test prompt kỹ với 30+ câu mẫu trước ship.

## 5. Forget về edge case "0 assets"
User chưa add gì → net worth = 0 → UI trông trống. Phải có empty state đẹp.

## 6. Net worth calculation không đúng
Test edge cases: asset mới add, user chưa có snapshot cũ, multi-currency future.

## 7. Storytelling mode infinite loop
User không nói exit keyword → stuck. Phải có timeout 15p.

## 8. Adapting UI theo level nhưng bug
Starter thấy HNW features → confused. Test carefully cho mỗi level.

---

# 🎯 Next Steps Sau Phase 3A

Sau khi Phase 3A ship + validation OK, tiếp theo là **Phase 3B — Market Intelligence**:

- Stock price auto-update (SSI/VNDIRECT API)
- Crypto price (CoinGecko)
- Gold price (SJC/PNJ scraping)
- Bank rate comparison
- Enhanced morning briefing với real-time data

Nhưng nếu validation show users không care về market data nhiều → skip 3B, jump thẳng Phase 4 (Investment Intelligence — rental tracking, goals).

Như mọi khi: **ship, measure, iterate**. 💚

---

**Good luck với Phase 3A! 🚀**
