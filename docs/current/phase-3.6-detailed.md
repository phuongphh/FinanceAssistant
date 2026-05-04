# Phase 3.6 — Menu UX Revamp (Chi Tiết Triển Khai)

> **Đây là phase mới được thêm vào sau Phase 3.5 để revamp menu UX cho match với Personal CFO positioning.**
> Phase này biến menu từ "flat list expense-tracker era" thành "hierarchical wealth-first interface".

> **Thời gian ước tính:** 1.5-2 tuần  
> **Mục tiêu cuối Phase:** Menu mới với 5 mảng chính (Tài sản, Chi tiêu, Dòng tiền, Mục tiêu, Thị trường), 3 levels hierarchy, adaptive descriptions theo wealth level, hybrid voice (buttons formal + descriptions Bé Tiền tone), và graceful exits to free-form queries.  
> **Điều kiện "Done":** User test mở /menu thấy structure mới ngay; navigation 3 levels smooth không stuck; mỗi sub-menu có example hint cho free-form alternative.

> **Prerequisites:** Phase 3.5 (intent layer) đã ship. Menu cần work song song với free-form queries, không replace.

---

## 🎯 Triết Lý Thiết Kế Phase 3.6

Đây là 5 nguyên lý quan trọng, đọc kỹ trước khi code:

### 1. "Menu là Bridge, Không Phải Primary Path"
Phase 3.5 đã làm cho user có thể hỏi free-form. Menu KHÔNG replace cái đó. Menu phục vụ:
- **Discoverability** — users mới không biết hỏi gì
- **Reliability** — buttons predictable
- **Accessibility** — tap > type khi rảnh tay
- **Education** — hint user về free-form alternative

→ Mỗi sub-menu phải có **graceful exit to free-form** ("hoặc hỏi mình thẳng: ...")

### 2. "Wealth-First, Not Expense-First"
Menu cũ bắt đầu với "Quét Gmail", "OCR Hóa đơn" — expense tracking era. Menu mới bắt đầu với **💎 Tài sản** — match Personal CFO positioning.

### 3. "Hybrid Voice — Formal Buttons, Warm Descriptions"
- **Buttons:** ngắn gọn, formal ("Tổng tài sản", "Thêm chi tiêu")
- **Descriptions:** Bé Tiền tone ấm áp ("mình giúp bạn theo dõi...")
- **Hints:** đầy personality ("hoặc hỏi mình thẳng nhé!")

### 4. "Adaptive Descriptions, Same Buttons"
Wealth level (từ Phase 3.5) shape **descriptions**, không shape **buttons**:
- Starter user thấy intro encouraging, simple language
- HNW user thấy intro professional, advanced concepts
- **Buttons identical across levels** → predictable UX

### 5. "Three Entry Points, Three Purposes"
Telegram bot có 3 ways user truy cập features. Mỗi cái serve khác nhau:

| Entry Point | Purpose | Example |
|-------------|---------|---------|
| **Bot menu button** (Telegram corner) | Commands list | `/start`, `/menu`, `/help` |
| **/menu command** | Rich interactive navigation | This phase's focus |
| **Dashboard button** | Visual data view (Mini App) | Net worth charts |

→ Phase 3.6 focus là `/menu` rich experience. Bot menu button đã có sẵn (chỉ update commands), Dashboard button không thay đổi.

---

## 📅 Phân Bổ Thời Gian (1.5-2 tuần)

| Tuần | Nội dung | Deliverable |
|------|----------|-------------|
| **Tuần 1** | Menu structure + Content (5 mảng + sub-menus) | Menu mới fully implemented, replace menu cũ |
| **Tuần 2 (1/2)** | Adaptive descriptions + Migration + Testing | Wealth-aware copy, deploy, user test |

---

## 🗂️ Cấu Trúc Thư Mục Mở Rộng

```
finance_assistant/
├── app/
│   ├── bot/
│   │   ├── handlers/
│   │   │   └── menu_handler.py             # ⭐ NEW (replace old menu)
│   │   ├── keyboards/
│   │   │   ├── main_menu.py                # ⭐ NEW - 5 categories
│   │   │   ├── submenu_assets.py           # ⭐ NEW
│   │   │   ├── submenu_expenses.py         # ⭐ NEW
│   │   │   ├── submenu_cashflow.py         # ⭐ NEW
│   │   │   ├── submenu_goals.py            # ⭐ NEW
│   │   │   └── submenu_market.py           # ⭐ NEW
│   │   └── formatters/
│   │       └── menu_formatter.py           # ⭐ NEW - adaptive intros
│   │
│   └── ...
│
├── content/
│   └── menu_copy.yaml                      # ⭐ NEW - All menu text
│
└── tests/
    └── test_menu/
        ├── test_navigation.py
        └── test_adaptive_copy.py
```

---

# 🎨 TUẦN 1: Menu Structure + Content

## 1.1 — Information Architecture (Hierarchy Tree)

```
LEVEL 1 — Main Menu (/menu)
├── 💎 Tài sản
│   ├── 📊 Tổng tài sản (Net Worth)
│   ├── 📈 Báo cáo chi tiết
│   ├── ➕ Thêm tài sản  ──────────► WIZARD (Level 3)
│   ├── ✏️ Sửa tài sản   ──────────► WIZARD (Level 3)
│   ├── 💡 Tư vấn tối ưu
│   └── ◀️ Quay về menu chính
│
├── 💸 Chi tiêu
│   ├── ➕ Thêm chi tiêu
│   ├── 📷 OCR hoá đơn
│   ├── 📊 Báo cáo chi tiêu
│   ├── 🏷️ Theo phân loại
│   └── ◀️ Quay về menu chính
│
├── 💰 Dòng tiền
│   ├── 📊 Tổng quan dòng tiền
│   ├── 💼 Thu nhập
│   ├── 📉 Chi tiêu vs Thu nhập
│   ├── 💎 Tỷ lệ tiết kiệm
│   └── ◀️ Quay về menu chính
│
├── 🎯 Mục tiêu
│   ├── 📋 Mục tiêu hiện tại
│   ├── ➕ Thêm mục tiêu  ─────────► WIZARD (Level 3)
│   ├── ✏️ Cập nhật tiến độ
│   ├── 💡 Gợi ý lộ trình
│   └── ◀️ Quay về menu chính
│
└── 📊 Thị trường
    ├── 🇻🇳 VN-Index hôm nay
    ├── 📈 Cổ phiếu quan tâm
    ├── ₿ Crypto
    ├── 🥇 Vàng SJC
    ├── 💡 Cơ hội đầu tư
    └── ◀️ Quay về menu chính
```

**Decision rationale:**

- **5 categories thay vì 6** — gộp "Đầu tư" vào "Tài sản" (tư vấn tối ưu portfolio hiện có) và "Thị trường" (cơ hội mới). Avoid overlap.
- **"Tư vấn tối ưu" trong Tài sản** — inward-looking advisor cho holdings hiện tại
- **"Cơ hội đầu tư" trong Thị trường** — outward-looking advisor cho new investments
- **Mỗi sub-menu có "◀️ Quay về"** — consistent escape route
- **Wizard sub-menus** (Thêm tài sản, Sửa tài sản, Thêm mục tiêu) → trigger existing wizards từ Phase 3A

---

## 1.2 — Content File: `menu_copy.yaml`

**Đây là file quan trọng nhất tuần 1.** Chứa toàn bộ text user-facing, dễ edit không cần deploy code.

### File: `content/menu_copy.yaml`

```yaml
# Menu copy — all user-facing text
# Format: each menu has 'intro' (4 wealth levels), 'buttons', 'hint'
# Placeholders: {name} = user.display_name

# ===========================================
# MAIN MENU (Level 1)
# ===========================================

main_menu:
  title:
    starter: "👋 Bé Tiền — Trợ lý tài chính của {name}"
    young_prof: "👋 Bé Tiền — Trợ lý tài chính của {name}"
    mass_affluent: "👋 Bé Tiền — Trợ lý CFO cá nhân của {name}"
    hnw: "👋 Bé Tiền — Personal CFO của anh/chị {name}"
  
  intro:
    starter: |
      Mình giúp {name} theo dõi tài sản, chi tiêu, và xây kế hoạch
      tài chính từng bước.
      
      Bạn muốn xem gì hôm nay?
    
    young_prof: |
      Mình giúp {name} quản lý tài sản và xây danh mục đầu tư
      vững mạnh.
      
      Bạn muốn xem gì hôm nay?
    
    mass_affluent: |
      Mình giúp {name} tối ưu hóa tài sản và đưa ra quyết định
      tài chính thông minh.
      
      Bạn muốn làm gì hôm nay?
    
    hnw: |
      Tổng quan tài chính cá nhân của anh/chị {name}.
      
      Anh/chị muốn xem mục nào?
  
  buttons:
    - label: "💎 Tài sản"
      callback: "menu:assets"
    - label: "💸 Chi tiêu"
      callback: "menu:expenses"
    - label: "💰 Dòng tiền"
      callback: "menu:cashflow"
    - label: "🎯 Mục tiêu"
      callback: "menu:goals"
    - label: "📊 Thị trường"
      callback: "menu:market"
  
  hint: |
    💡 **Mẹo:** Bạn có thể hỏi mình trực tiếp như:
    "tài sản của tôi có gì?"
    "tháng này tiêu bao nhiêu?"
    "VNM giá hôm nay?"
    
    Không cần menu — hỏi tự nhiên là được!

# ===========================================
# SUB-MENU: TÀI SẢN (Level 2)
# ===========================================

submenu_assets:
  title: "💎 TÀI SẢN"
  
  intro:
    starter: |
      Đây là nơi mình giúp {name} theo dõi tài sản — tiền mặt,
      đầu tư, BĐS, vàng...
      
      Mỗi tài sản bạn thêm sẽ giúp mình tính tổng giá trị và
      theo dõi sự thay đổi qua thời gian.
    
    young_prof: |
      Theo dõi tổng tài sản và phân bổ đầu tư của {name}.
      
      Mỗi loại tài sản đều được track riêng để bạn biết
      đâu đang tăng, đâu đang giảm.
    
    mass_affluent: |
      Quản lý tổng giá trị ròng và phân bổ tài sản của {name}.
      
      Bao gồm tư vấn rebalance dựa trên portfolio hiện tại.
    
    hnw: |
      Tổng quan tài sản và performance metrics của anh/chị.
      
      Bao gồm tư vấn tối ưu hóa allocation.
  
  buttons:
    - label: "📊 Tổng tài sản"
      callback: "menu:assets:net_worth"
      description: "Xem net worth hiện tại + breakdown theo loại"
    
    - label: "📈 Báo cáo chi tiết"
      callback: "menu:assets:report"
      description: "Trend 30/90/365 ngày, top performer, history"
    
    - label: "➕ Thêm tài sản"
      callback: "menu:assets:add"
      description: "Wizard thêm cash, stock, BĐS, crypto, vàng"
    
    - label: "✏️ Sửa tài sản"
      callback: "menu:assets:edit"
      description: "Cập nhật giá trị, xóa, đánh dấu đã bán"
    
    - label: "💡 Tư vấn tối ưu"
      callback: "menu:assets:advisor"
      description: "Phân tích allocation, gợi ý rebalance"
    
    - label: "◀️ Quay về"
      callback: "menu:main"
  
  hint: |
    💡 Hoặc hỏi nhanh:
    "tài sản của tôi có gì?"
    "tổng tài sản tôi bao nhiêu?"
    "portfolio chứng khoán của tôi"

# ===========================================
# SUB-MENU: CHI TIÊU (Level 2)
# ===========================================

submenu_expenses:
  title: "💸 CHI TIÊU"
  
  intro:
    starter: |
      Theo dõi chi tiêu hàng ngày của {name}.
      
      Mình chỉ track những khoản đáng kể (>200k) để không
      làm phiền bạn với từng ly cafe nhỏ.
    
    young_prof: |
      Quản lý chi tiêu và phát hiện pattern không hợp lý.
      
      Mình focus vào khoản từ 200k trở lên — vừa đủ để
      hiểu cashflow mà không phải ghi mọi thứ.
    
    mass_affluent: |
      Theo dõi cashflow categories và identify large expenses.
      
      Bot tự động extract từ storytelling và OCR hóa đơn.
    
    hnw: |
      Quản lý chi tiêu lớn và analytics theo loại.
  
  buttons:
    - label: "➕ Thêm chi tiêu"
      callback: "menu:expenses:add"
      description: "Ghi giao dịch mới — text hoặc voice"
    
    - label: "📷 OCR hoá đơn"
      callback: "menu:expenses:ocr"
      description: "Chụp hóa đơn, mình tự đọc"
    
    - label: "📊 Báo cáo chi tiêu"
      callback: "menu:expenses:report"
      description: "Tổng quan tháng này, theo loại, trend"
    
    - label: "🏷️ Theo phân loại"
      callback: "menu:expenses:by_category"
      description: "Ăn uống, di chuyển, sức khỏe..."
    
    - label: "◀️ Quay về"
      callback: "menu:main"
  
  hint: |
    💡 Hoặc hỏi nhanh:
    "chi tiêu tháng này"
    "chi cho ăn uống tuần qua"
    "vừa chi 200k cafe"

# ===========================================
# SUB-MENU: DÒNG TIỀN (Level 2)
# ===========================================

submenu_cashflow:
  title: "💰 DÒNG TIỀN"
  
  intro:
    starter: |
      Dòng tiền = thu nhập - chi tiêu của {name}.
      
      Đây là chỉ số quan trọng nhất để biết bạn có đang
      tiết kiệm được tiền không.
    
    young_prof: |
      Theo dõi thu - chi và tỷ lệ tiết kiệm của {name}.
      
      Tỷ lệ tiết kiệm 20-30% là healthy cho phần lớn người trẻ.
    
    mass_affluent: |
      Quản lý dòng tiền tổng và optimize savings rate.
      
      Bao gồm passive income (dividend, lãi tiết kiệm).
    
    hnw: |
      Dòng tiền active + passive, runway analysis.
  
  buttons:
    - label: "📊 Tổng quan dòng tiền"
      callback: "menu:cashflow:overview"
      description: "Thu, chi, tiết kiệm tháng này"
    
    - label: "💼 Thu nhập"
      callback: "menu:cashflow:income"
      description: "Lương, thụ động, các nguồn khác"
    
    - label: "📉 Chi tiêu vs Thu nhập"
      callback: "menu:cashflow:compare"
      description: "Biểu đồ so sánh 6 tháng qua"
    
    - label: "💎 Tỷ lệ tiết kiệm"
      callback: "menu:cashflow:saving_rate"
      description: "% thu nhập bạn tiết kiệm được"
    
    - label: "◀️ Quay về"
      callback: "menu:main"
  
  hint: |
    💡 Hoặc hỏi nhanh:
    "thu nhập của tôi"
    "tháng này dư bao nhiêu?"
    "tỷ lệ tiết kiệm của tôi"

# ===========================================
# SUB-MENU: MỤC TIÊU (Level 2)
# ===========================================

submenu_goals:
  title: "🎯 MỤC TIÊU"
  
  intro:
    starter: |
      Đặt mục tiêu tài chính giúp {name} có động lực
      và roadmap rõ ràng.
      
      Bắt đầu nhỏ — tiết kiệm 10tr, mua xe máy, du lịch...
    
    young_prof: |
      Quản lý mục tiêu trung-dài hạn của {name}.
      
      Mình giúp tính toán cần tiết kiệm bao nhiêu/tháng
      để đạt được trong thời gian mong muốn.
    
    mass_affluent: |
      Theo dõi mục tiêu và optimize lộ trình đạt được.
      
      Bao gồm tư vấn investment strategy phù hợp với từng goal.
    
    hnw: |
      Mục tiêu dài hạn, retirement planning, estate planning.
  
  buttons:
    - label: "📋 Mục tiêu hiện tại"
      callback: "menu:goals:list"
      description: "Tất cả goals đang active + tiến độ"
    
    - label: "➕ Thêm mục tiêu"
      callback: "menu:goals:add"
      description: "Đặt mục tiêu mới với deadline"
    
    - label: "✏️ Cập nhật tiến độ"
      callback: "menu:goals:update"
      description: "Thêm tiền vào goal đang track"
    
    - label: "💡 Gợi ý lộ trình"
      callback: "menu:goals:advisor"
      description: "Cần tiết kiệm bao nhiêu/tháng?"
    
    - label: "◀️ Quay về"
      callback: "menu:main"
  
  hint: |
    💡 Hoặc hỏi nhanh:
    "mục tiêu của tôi"
    "muốn mua xe cần làm gì?"
    "lộ trình mua nhà"

# ===========================================
# SUB-MENU: THỊ TRƯỜNG (Level 2)
# ===========================================

submenu_market:
  title: "📊 THỊ TRƯỜNG"
  
  intro:
    starter: |
      Cập nhật giá thị trường và học hỏi về đầu tư.
      
      Bắt đầu xem những mã phổ biến: VNM, VIC, BTC...
    
    young_prof: |
      Theo dõi market data và tìm cơ hội đầu tư phù hợp.
      
      Bao gồm gợi ý cho người mới bắt đầu.
    
    mass_affluent: |
      Market intelligence và investment opportunities.
      
      Tin tức được lọc theo holdings hiện tại của {name}.
    
    hnw: |
      Phân tích thị trường chuyên sâu và investment ideas.
  
  buttons:
    - label: "🇻🇳 VN-Index hôm nay"
      callback: "menu:market:vnindex"
      description: "Chỉ số chính, top gainer/loser"
    
    - label: "📈 Cổ phiếu quan tâm"
      callback: "menu:market:stocks"
      description: "Mã bạn sở hữu + watchlist"
    
    - label: "₿ Crypto"
      callback: "menu:market:crypto"
      description: "BTC, ETH, top coins"
    
    - label: "🥇 Vàng SJC"
      callback: "menu:market:gold"
      description: "Giá vàng SJC, PNJ"
    
    - label: "💡 Cơ hội đầu tư"
      callback: "menu:market:advisor"
      description: "Gợi ý đầu tư mới dựa trên thị trường"
    
    - label: "◀️ Quay về"
      callback: "menu:main"
  
  hint: |
    💡 Hoặc hỏi nhanh:
    "VNM giá bao nhiêu?"
    "BTC hôm nay thế nào?"
    "nên đầu tư gì?"
```

---

## 1.3 — Menu Formatter (Adaptive Logic)

### File: `app/bot/formatters/menu_formatter.py`

```python
"""
Menu formatter with wealth-level adaptive descriptions.
Same buttons across all levels, different intro copy.
"""

import yaml
from pathlib import Path
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.wealth.ladder import detect_level, WealthLevel
from app.wealth.services.net_worth_calculator import NetWorthCalculator


class MenuFormatter:
    def __init__(self):
        self._copy = self._load_copy()
    
    def _load_copy(self):
        path = Path("content/menu_copy.yaml")
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    async def format_main_menu(self, user) -> tuple[str, InlineKeyboardMarkup]:
        """Build main menu text + keyboard."""
        # Detect wealth level
        net_worth = await NetWorthCalculator().calculate(user.id)
        level = detect_level(net_worth.total).value
        
        config = self._copy["main_menu"]
        name = user.display_name or "bạn"
        
        # Build text
        title = config["title"][level].format(name=name)
        intro = config["intro"][level].format(name=name)
        hint = config["hint"]
        
        text = f"{title}\n\n{intro}\n\n{hint}"
        
        # Build keyboard (2 columns layout for main menu)
        buttons = config["buttons"]
        rows = []
        for i in range(0, len(buttons), 2):
            row = [
                InlineKeyboardButton(b["label"], callback_data=b["callback"])
                for b in buttons[i:i+2]
            ]
            rows.append(row)
        
        return text, InlineKeyboardMarkup(rows)
    
    async def format_submenu(self, user, category: str) -> tuple[str, InlineKeyboardMarkup]:
        """Build sub-menu for a category."""
        config_key = f"submenu_{category}"
        if config_key not in self._copy:
            raise ValueError(f"Unknown category: {category}")
        
        config = self._copy[config_key]
        
        # Detect level for adaptive intro
        net_worth = await NetWorthCalculator().calculate(user.id)
        level = detect_level(net_worth.total).value
        name = user.display_name or "bạn"
        
        title = config["title"]
        intro = config["intro"][level].format(name=name)
        hint = config["hint"]
        
        text = f"{title}\n\n{intro}\n\n{hint}"
        
        # Build keyboard (1 column for sub-menus — vertical layout)
        buttons = config["buttons"]
        rows = []
        for b in buttons:
            rows.append([InlineKeyboardButton(b["label"], callback_data=b["callback"])])
        
        return text, InlineKeyboardMarkup(rows)
```

---

## 1.4 — Menu Handler (Routing)

### File: `app/bot/handlers/menu_handler.py`

```python
"""
Handle menu navigation across 3 levels.
Replaces old flat menu logic.
"""

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.formatters.menu_formatter import MenuFormatter
from app.services.user_service import UserService


_formatter = MenuFormatter()
_user_service = UserService()


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point: /menu command."""
    user_id = update.effective_user.id
    user = await _user_service.get_by_telegram_id(user_id)
    
    text, keyboard = await _formatter.format_main_menu(user)
    
    await update.message.reply_text(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all menu:* callback queries."""
    query = update.callback_query
    await query.answer()  # Dismiss loading state
    
    user_id = query.from_user.id
    user = await _user_service.get_by_telegram_id(user_id)
    
    callback_data = query.data
    
    # Parse callback
    parts = callback_data.split(":")
    # parts[0] = "menu"
    # parts[1] = category or "main"
    # parts[2] = action (optional)
    
    if len(parts) == 2:
        # Top-level navigation
        if parts[1] == "main":
            text, keyboard = await _formatter.format_main_menu(user)
        else:
            # Sub-menu (assets, expenses, etc.)
            text, keyboard = await _formatter.format_submenu(user, parts[1])
        
        # Edit message in place (smooth navigation)
        await query.edit_message_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        return
    
    # Action-level callback (e.g., menu:assets:add)
    category = parts[1]
    action = parts[2]
    
    await _route_action(query, user, category, action)


async def _route_action(query, user, category: str, action: str):
    """Route to specific action handler."""
    
    # Map action callbacks to existing handlers
    action_map = {
        # Assets
        ("assets", "net_worth"): _show_net_worth,
        ("assets", "report"): _show_assets_report,
        ("assets", "add"): _start_add_asset_wizard,
        ("assets", "edit"): _start_edit_asset_wizard,
        ("assets", "advisor"): _show_assets_advisor,
        
        # Expenses
        ("expenses", "add"): _start_add_expense,
        ("expenses", "ocr"): _start_ocr_flow,
        ("expenses", "report"): _show_expense_report,
        ("expenses", "by_category"): _show_expense_by_category,
        
        # Cashflow
        ("cashflow", "overview"): _show_cashflow_overview,
        ("cashflow", "income"): _show_income,
        ("cashflow", "compare"): _show_compare_chart,
        ("cashflow", "saving_rate"): _show_saving_rate,
        
        # Goals
        ("goals", "list"): _show_goals,
        ("goals", "add"): _start_add_goal_wizard,
        ("goals", "update"): _start_update_goal,
        ("goals", "advisor"): _show_goals_advisor,
        
        # Market
        ("market", "vnindex"): _show_vnindex,
        ("market", "stocks"): _show_stocks,
        ("market", "crypto"): _show_crypto,
        ("market", "gold"): _show_gold,
        ("market", "advisor"): _show_market_advisor,
    }
    
    handler = action_map.get((category, action))
    if not handler:
        await query.edit_message_text(
            "🚧 Tính năng đang phát triển. Hỏi mình trực tiếp được không?",
        )
        return
    
    await handler(query, user)


# === Action handlers (each calls existing service) ===

async def _show_net_worth(query, user):
    """Reuse Phase 3.5 query_assets handler."""
    from app.intent.handlers.query_assets import QueryAssetsHandler
    from app.intent.intents import IntentResult, IntentType
    
    intent = IntentResult(
        intent=IntentType.QUERY_ASSETS,
        confidence=1.0,
        raw_text="[from menu]",
        parameters={},
    )
    handler = QueryAssetsHandler()
    response = await handler.handle(intent, user)
    
    await query.edit_message_text(response, parse_mode="Markdown")


async def _start_add_asset_wizard(query, user):
    """Trigger Phase 3A asset wizard."""
    from app.bot.handlers.asset_entry import start_asset_entry_wizard
    # Note: existing wizard expects Update, may need adapter
    # ... implementation
    pass


# ... similar for all other actions
```

---

## 1.5 — Update Bot Menu Button (Telegram Native)

Telegram bot menu button (corner top) là native Telegram feature. Update commands list:

### File: `app/bot/setup_commands.py`

```python
"""
Set up Telegram bot menu commands.
Run once on deploy.
"""

from telegram import BotCommand


BOT_COMMANDS = [
    BotCommand("start", "Bắt đầu / Onboarding"),
    BotCommand("menu", "Menu chính"),
    BotCommand("help", "Hướng dẫn sử dụng"),
    BotCommand("dashboard", "Mở Mini App dashboard"),
]


async def setup_bot_commands(bot):
    """Register commands with Telegram."""
    await bot.set_my_commands(BOT_COMMANDS)
```

**Important:** 4 commands này là **shortcut**, không phải replacement của /menu rich. User tap bot menu button → see commands → tap `/menu` → see rich inline menu.

---

## ✅ Checklist Cuối Tuần 1

- [ ] `content/menu_copy.yaml` đầy đủ 1 main menu + 5 sub-menus với 4 wealth levels intro
- [ ] `MenuFormatter` hoạt động — adaptive intro by level
- [ ] `MenuHandler` route tất cả menu:* callbacks
- [ ] 3-level navigation smooth: main → sub → action
- [ ] "◀️ Quay về" buttons consistent ở mọi sub-menu
- [ ] Edit message in place (không spam new messages khi navigate)
- [ ] Bot menu button (Telegram corner) updated với 4 core commands
- [ ] Tất cả existing wizards (Thêm tài sản, OCR, etc.) vẫn work qua action handlers
- [ ] Old menu (8 buttons flat) **completely replaced**
- [ ] Visual consistency: emojis match, formatting consistent

---

# 🎨 TUẦN 2 (1/2): Adaptive Polish + Migration + Testing

## 2.1 — Wealth Level Test Matrix

Test menu với 4 mock users (1 per level) để verify adaptive descriptions work:

| User | Level | Net Worth | Expected Main Menu Title |
|------|-------|-----------|--------------------------|
| Minh | starter | 17tr | "Trợ lý tài chính" |
| Hà | young_prof | 140tr | "Trợ lý tài chính" |
| Phương | mass_affluent | 4.5 tỷ | "Trợ lý CFO cá nhân" |
| Anh Tùng | hnw | 13 tỷ | "Personal CFO của anh/chị" |

For each user, trigger `/menu` → screenshot main menu → verify title + intro adapt correctly.

Repeat for each sub-menu (5 sub-menus × 4 users = 20 screenshots total).

---

## 2.2 — Migration Strategy (Hard Cutover)

Bạn đã chọn **option A — hard cutover**. Implementation plan:

### Pre-deploy checklist

- [ ] Old menu code archived (không xóa, comment với date)
- [ ] All callbacks `menu_old:*` redirect to new menu (graceful fallback nếu user tap old button)
- [ ] Analytics event `menu_revamp_deployed` fired on first user interaction
- [ ] Rollback plan documented

### Deploy steps

1. **Pre-deploy announcement** (optional — 1 day before):
   ```
   📢 Bé Tiền sắp được nâng cấp giao diện mới!
   
   Menu sẽ rõ ràng hơn với 5 mảng:
   💎 Tài sản • 💸 Chi tiêu • 💰 Dòng tiền • 🎯 Mục tiêu • 📊 Thị trường
   
   Cập nhật vào ngày mai 7h sáng. Mọi tính năng vẫn còn — 
   chỉ tổ chức gọn hơn thôi!
   ```

2. **Deploy** (off-peak hour, e.g., 7 AM):
   - Push new menu code
   - Update bot commands
   - Run smoke test (1 query each category)

3. **Post-deploy notification** (within 1 hour):
   ```
   ✨ Menu mới đã sẵn sàng!
   
   Gõ /menu để khám phá. Hoặc cứ hỏi mình tự nhiên 
   như cũ — mình hiểu mà 😊
   ```

### Rollback trigger

Rollback nếu trong 4h sau deploy:
- Error rate >5%
- User complaints >3
- Critical flow broken (e.g., wizard không trigger)

---

## 2.3 — User Testing (3 users, 1 day)

Lightweight user test:
- 1 Starter, 1 Mass Affluent, 1 HNW
- Each spends 10-15 min exploring new menu
- Tasks:
  1. Tìm net worth của bạn
  2. Xem chi tiêu tháng này theo loại
  3. Thêm 1 mục tiêu mới
  4. Check VNM hôm nay
- Note: time to complete each task, confusion points, "feel" of menu

### Success metrics

- ✅ All 3 users complete all 4 tasks
- ✅ <2 minutes average per task
- ✅ 0 users say "menu cũ tốt hơn"
- ✅ ≥2 users notice the warmer tone

---

## 2.4 — Cleanup & Archive

After successful deploy:

- [ ] Old menu code → archive folder với date stamp
- [ ] Old menu callbacks → graceful redirects (1 month) → remove
- [ ] Update CLAUDE.md: replace menu screenshot reference, update folder structure
- [ ] Update README.md if needed
- [ ] Update `docs/current/strategy.md` — mention menu UX revamp completed

---

## ✅ Checklist Cuối Tuần 2

- [ ] All 4 wealth levels tested with screenshots
- [ ] Migration deployed successfully
- [ ] 3-user user test completed with positive feedback
- [ ] No regressions in existing flows (wizards, briefing, intent pipeline)
- [ ] Analytics confirm users navigating menu (engagement metric)
- [ ] Old menu code archived
- [ ] Documentation updated

---

# 🚧 Bẫy Thường Gặp Phase 3.6

## 1. Forget about state persistence
User taps "💎 Tài sản" → sub-menu shown via `edit_message_text`. If user navigates back via Telegram chat history, old message state may not match current menu. → **Always render fresh state on /menu trigger.**

## 2. Telegram message length limit
Each menu message has intro + buttons. Total can exceed 4096 chars. Test with HNW level (most verbose intro). → **Keep intros under 200 words.**

## 3. Callback data 64-char limit
Telegram callback_data max 64 chars. Format `menu:category:action` keeps short. → **Don't add params in callback** — store in user_data instead.

## 4. Mobile button text overflow
Long button labels wrap awkwardly on small screens. Test on iPhone SE (smallest). → **Keep button labels ≤16 characters.**

## 5. Adaptive intro mismatch
Net worth changes → wealth level changes → intro changes. If user's level just shifted (e.g., 29tr → 31tr), they'll see different intro. → **This is expected** — don't try to "lock" level.

## 6. Wizard re-entry issue
User in middle of asset wizard, taps /menu → state confusion. → **Check wizard state before showing menu, offer "Continue wizard" option.**

## 7. Free-form hint becomes wallpaper
If hint always same, users blind to it. → **Rotate examples** or A/B test different formulations.

## 8. Personality drift
Buttons formal, descriptions warm — easy to lose balance. → **Have native VN reviewer check copy** for tone consistency.

---

# 🎯 Exit Criteria Phase 3.6

Phase 3.6 ready to ship to all users when:

- [ ] All 5 main categories functional with 3-5 sub-actions each
- [ ] 3 entry points work (bot menu button, /menu, dashboard)
- [ ] Adaptive intros differ across 4 wealth levels (verified by screenshots)
- [ ] Free-form hints visible in every sub-menu
- [ ] Navigation 3 levels smooth (main → sub → action)
- [ ] All Phase 3A wizards reachable via menu
- [ ] All Phase 3.5 intent handlers reachable via menu
- [ ] Mobile + desktop tested
- [ ] User testing positive (≥3 users)
- [ ] No regressions
- [ ] Old menu fully retired

---

# 📈 Success Metrics (Track from Day 1)

**Engagement:**
- /menu invocations per user per day (baseline vs after revamp)
- Time spent in menu before exit (deeper exploration?)
- % users tap sub-menu vs only main (depth)

**Discovery:**
- % users discover new feature (e.g., "Dòng tiền") within 1 week
- Free-form query rate **after** menu revamp (should INCREASE — menu educates)

**Sentiment:**
- Direct user feedback after deploy
- Support requests about navigation (should DECREASE)

**Performance:**
- /menu response time <500ms
- Edit message latency <300ms

---

**Phase 3.6 transforms menu from "expense tracker era artifact" to "Personal CFO interface". Sau phase này, mọi pixel của Bé Tiền match positioning — wealth-first, warm, adaptive. 🎨💚**
