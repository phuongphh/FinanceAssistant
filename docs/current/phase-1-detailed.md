# Phase 1 — Tối Đa Hóa UX Trong Telegram (Chi Tiết Triển Khai)

> **Thời gian ước tính:** 3-4 tuần  
> **Mục tiêu cuối Phase:** Bot trông chuyên nghiệp, mọi thao tác đều 1-chạm, có Mini App dashboard cơ bản, brand identity rõ ràng.  
> **Điều kiện "Done":** Chính bạn khi dùng bot cảm thấy "sản phẩm này đẹp và được đầu tư", sẵn sàng cho 5-10 friends dùng thử.

---

## 📅 Phân Bổ Thời Gian 4 Tuần

| Tuần | Nội dung chính | Deliverable |
|------|---------------|-------------|
| **Tuần 1** | Rich Message Design + Emoji system | `message_formatter.py` hoàn chỉnh, bot trả lời đẹp |
| **Tuần 2** | Inline Buttons + Callback handlers | User có thể edit/delete/categorize bằng tap |
| **Tuần 3** | Telegram Mini App (Dashboard v1) | Mini App mở được, hiển thị báo cáo tháng cơ bản |
| **Tuần 4** | Visual Identity + Polish + Testing | Mascot, tone writing, bug fixing, friends testing |

---

# 🗂️ Cấu Trúc Thư Mục Đề Xuất

Dựa trên stack FastAPI + PostgreSQL + Telegram Bot của bạn, tôi gợi ý cấu trúc:

```
finance_assistant/
├── app/
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # Config, env vars
│   ├── database.py                # SQLAlchemy setup
│   │
│   ├── bot/                       # Telegram Bot logic
│   │   ├── __init__.py
│   │   ├── handlers/              # Message/callback handlers
│   │   │   ├── __init__.py
│   │   │   ├── transaction.py     # Handle new transactions
│   │   │   ├── callbacks.py       # Inline button callbacks
│   │   │   ├── commands.py        # /start, /report, /help
│   │   │   └── onboarding.py      # (Phase 2)
│   │   ├── formatters/            # ⭐ NEW - Message formatting
│   │   │   ├── __init__.py
│   │   │   ├── message_formatter.py
│   │   │   ├── progress_bar.py
│   │   │   └── templates.py       # Tin nhắn templates
│   │   ├── keyboards/             # ⭐ NEW - Inline keyboards
│   │   │   ├── __init__.py
│   │   │   ├── transaction_keyboard.py
│   │   │   └── common.py
│   │   └── bot_instance.py        # Bot singleton
│   │
│   ├── miniapp/                   # ⭐ NEW - Telegram Mini App
│   │   ├── static/
│   │   │   ├── css/style.css
│   │   │   ├── js/dashboard.js
│   │   │   └── js/auth.js
│   │   ├── templates/
│   │   │   ├── dashboard.html
│   │   │   └── budget.html
│   │   └── routes.py              # FastAPI routes cho Mini App
│   │
│   ├── models/                    # DB models
│   │   ├── user.py
│   │   ├── transaction.py
│   │   └── category.py
│   │
│   ├── services/                  # Business logic
│   │   ├── transaction_service.py
│   │   ├── report_service.py
│   │   └── user_service.py
│   │
│   └── config/
│       ├── categories.py          # ⭐ NEW - Category + emoji map
│       └── emoji_map.py           # ⭐ NEW
│
├── tests/
│   ├── test_formatters.py
│   ├── test_callbacks.py
│   └── test_miniapp_auth.py
│
├── alembic/                       # DB migrations
└── docker-compose.yml
```

**⭐ = folder/file mới cần tạo trong Phase 1**

---

# 🎨 TUẦN 1: Rich Message Design

## 1.1 — Cấu Hình Categories & Emojis

### File: `app/config/categories.py`

Đây là file nền tảng — mọi module khác sẽ import từ đây.

```python
"""
Định nghĩa categories và emoji cho toàn hệ thống.
Một category = một emoji cố định, nhất quán.
"""

from enum import Enum
from dataclasses import dataclass


@dataclass
class Category:
    code: str           # Dùng trong DB, callback_data
    name_vi: str        # Hiển thị cho user VN
    emoji: str          # Emoji nhất quán
    color_hex: str      # Dùng trong Mini App charts


CATEGORIES = {
    "food": Category("food", "Ăn uống", "🍜", "#FF6B6B"),
    "transport": Category("transport", "Di chuyển", "🚗", "#4ECDC4"),
    "housing": Category("housing", "Nhà cửa", "🏠", "#95E1D3"),
    "shopping": Category("shopping", "Mua sắm", "👕", "#F38181"),
    "health": Category("health", "Sức khỏe", "💊", "#AA96DA"),
    "education": Category("education", "Giáo dục", "📚", "#FCBAD3"),
    "entertainment": Category("entertainment", "Giải trí", "🎮", "#FFFFD2"),
    "saving": Category("saving", "Tiết kiệm", "💰", "#A8E6CF"),
    "investment": Category("investment", "Đầu tư", "📊", "#3D5A80"),
    "gift": Category("gift", "Quà tặng", "🎁", "#EE6C4D"),
    "utility": Category("utility", "Tiện ích", "⚡", "#F9ED69"),
    "transfer": Category("transfer", "Chuyển khoản", "🔄", "#B0B0B0"),
    "other": Category("other", "Khác", "📌", "#808080"),
}


def get_category(code: str) -> Category:
    """Lấy category, fallback về 'other' nếu không tìm thấy."""
    return CATEGORIES.get(code, CATEGORIES["other"])


def get_all_categories() -> list[Category]:
    return list(CATEGORIES.values())
```

**Tại sao thiết kế thế này:**
- `Enum` + `dataclass` giúp type-safe, IDE autocomplete tốt
- Tất cả thông tin về 1 category nằm 1 chỗ — thêm category mới chỉ sửa 1 file
- `color_hex` để Phase 3 dùng cho Mini App charts mà không cần re-design

---

## 1.2 — Progress Bar Generator

### File: `app/bot/formatters/progress_bar.py`

```python
"""
Tạo Unicode progress bar cho tin nhắn.
Dùng nhân vật block để nhìn đẹp trên Telegram.
"""


def make_progress_bar(
    current: float,
    total: float,
    width: int = 10,
    filled_char: str = "█",
    empty_char: str = "░"
) -> str:
    """
    Tạo progress bar dạng ████████░░
    
    Args:
        current: Giá trị hiện tại
        total: Giá trị tối đa
        width: Độ rộng bar (số ký tự)
        filled_char: Ký tự phần đã đầy
        empty_char: Ký tự phần trống
    
    Returns:
        String dạng "████████░░ 80%"
    
    Examples:
        >>> make_progress_bar(80, 100)
        '████████░░ 80%'
        >>> make_progress_bar(150, 100)  # Vượt quá 100%
        '██████████ 150%'
    """
    if total <= 0:
        return empty_char * width + " 0%"
    
    percentage = (current / total) * 100
    filled_count = min(width, int((current / total) * width))
    empty_count = width - filled_count
    
    bar = filled_char * filled_count + empty_char * empty_count
    return f"{bar} {percentage:.0f}%"


def make_category_bar(amount: float, max_amount: float, width: int = 10) -> str:
    """
    Progress bar cho category breakdown.
    Tương tự nhưng không hiển thị %.
    """
    if max_amount <= 0:
        return "░" * width
    filled = min(width, int((amount / max_amount) * width))
    return "█" * filled + "░" * (width - filled)
```

### Test: `tests/test_progress_bar.py`

```python
from app.bot.formatters.progress_bar import make_progress_bar


def test_progress_bar_half():
    result = make_progress_bar(50, 100, width=10)
    assert result == "█████░░░░░ 50%"


def test_progress_bar_full():
    result = make_progress_bar(100, 100, width=10)
    assert result == "██████████ 100%"


def test_progress_bar_over():
    result = make_progress_bar(150, 100, width=10)
    # Khi vượt 100%, bar vẫn full nhưng % hiển thị đúng
    assert "150%" in result


def test_progress_bar_zero_total():
    result = make_progress_bar(0, 0)
    assert "0%" in result
```

---

## 1.3 — Number Formatting (Tiền Việt)

### File: `app/bot/formatters/money.py`

Format số tiền kiểu Việt Nam rất quan trọng — không nên hiển thị "150000 VND" mà phải là "150k" hoặc "150,000đ".

```python
def format_money_short(amount: float) -> str:
    """
    Format ngắn gọn kiểu Việt Nam.
    
    Examples:
        >>> format_money_short(45000)
        '45k'
        >>> format_money_short(1500000)
        '1.5tr'
        >>> format_money_short(25000000)
        '25tr'
        >>> format_money_short(1200000000)
        '1.2 tỷ'
    """
    if amount < 1000:
        return f"{int(amount)}đ"
    elif amount < 1_000_000:
        k = amount / 1000
        if k == int(k):
            return f"{int(k)}k"
        return f"{k:.1f}k".rstrip("0").rstrip(".") + "k" if "." in f"{k:.1f}" else f"{int(k)}k"
    elif amount < 1_000_000_000:
        m = amount / 1_000_000
        if m == int(m):
            return f"{int(m)}tr"
        return f"{m:.1f}tr"
    else:
        b = amount / 1_000_000_000
        return f"{b:.1f} tỷ"


def format_money_full(amount: float) -> str:
    """
    Format đầy đủ với dấu phẩy.
    
    Examples:
        >>> format_money_full(45000)
        '45,000đ'
        >>> format_money_full(1500000)
        '1,500,000đ'
    """
    return f"{int(amount):,}đ"
```

**Khi nào dùng short vs full:**
- **Short** (`45k`, `1.5tr`): Trong progress bar, báo cáo tóm tắt, nơi không gian hẹp
- **Full** (`45,000đ`): Trong tin nhắn xác nhận giao dịch, nơi cần chính xác tuyệt đối

---

## 1.4 — Message Templates

### File: `app/bot/formatters/templates.py`

Đây là trái tim của rich messaging. Tất cả tin nhắn bot gửi đi đều từ đây.

```python
"""
Templates cho mọi tin nhắn bot gửi.
Nguyên tắc: Một function = một loại tin nhắn.
"""

from datetime import datetime
from app.config.categories import get_category
from app.bot.formatters.progress_bar import make_progress_bar, make_category_bar
from app.bot.formatters.money import format_money_short, format_money_full


def format_transaction_confirmation(
    merchant: str,
    amount: float,
    category_code: str,
    location: str = None,
    time: datetime = None,
    daily_spent: float = None,
    daily_budget: float = None,
) -> str:
    """
    Tin nhắn xác nhận sau khi ghi giao dịch thành công.
    
    Output:
    ✅ Ghi xong!
    
    🍜 Phở Bát Đàn  —  45,000đ
    📍 Hà Nội  •  12:15
    
    💰 Hôm nay: 215k / 400k
       █████░░░░░ 54%
    
    Còn 185k cho hôm nay 👌
    """
    cat = get_category(category_code)
    
    lines = ["✅ Ghi xong!", ""]
    
    # Dòng giao dịch chính
    lines.append(f"{cat.emoji} {merchant}  —  {format_money_full(amount)}")
    
    # Dòng context (location, time)
    context_parts = []
    if location:
        context_parts.append(f"📍 {location}")
    if time:
        context_parts.append(time.strftime("%H:%M"))
    if context_parts:
        lines.append("  •  ".join(context_parts))
    
    lines.append("")
    
    # Progress bar ngân sách (nếu có)
    if daily_spent is not None and daily_budget is not None and daily_budget > 0:
        bar = make_progress_bar(daily_spent, daily_budget, width=10)
        lines.append(f"💰 Hôm nay: {format_money_short(daily_spent)} / {format_money_short(daily_budget)}")
        lines.append(f"   {bar}")
        lines.append("")
        
        remaining = daily_budget - daily_spent
        if remaining > 0:
            lines.append(f"Còn {format_money_short(remaining)} cho hôm nay 👌")
        elif remaining > -100000:  # Vượt ít
            lines.append(f"Đã vượt ngân sách {format_money_short(-remaining)} 🫣")
        else:  # Vượt nhiều
            lines.append(f"Vượt ngân sách {format_money_short(-remaining)} — cần chú ý 😅")
    
    return "\n".join(lines)


def format_daily_summary(
    date: datetime,
    total_spent: float,
    transaction_count: int,
    breakdown: list[tuple[str, float]],  # [(category_code, amount), ...]
    vs_average_pct: float = None,  # % chênh so với trung bình
) -> str:
    """
    Báo cáo cuối ngày.
    
    Output:
    🌙 Tóm tắt ngày 15/04
    
    Tổng chi: 485,000đ (4 giao dịch)
    
    🍜 Ăn uống      245k  ████████░░
    🚗 Di chuyển    150k  █████░░░░░
    👕 Mua sắm       90k  ███░░░░░░░
    
    So với trung bình: +12% ↑
    """
    lines = [
        f"🌙 Tóm tắt ngày {date.strftime('%d/%m')}",
        "",
        f"Tổng chi: {format_money_full(total_spent)} ({transaction_count} giao dịch)",
        "",
    ]
    
    if breakdown:
        # Sort giảm dần theo amount
        breakdown_sorted = sorted(breakdown, key=lambda x: x[1], reverse=True)
        max_amount = breakdown_sorted[0][1]
        
        for cat_code, amount in breakdown_sorted[:5]:  # Top 5
            cat = get_category(cat_code)
            bar = make_category_bar(amount, max_amount, width=10)
            # Căn chỉnh tên category (padding cho đẹp)
            name_padded = f"{cat.emoji} {cat.name_vi}".ljust(15)
            amount_str = format_money_short(amount).rjust(5)
            lines.append(f"{name_padded} {amount_str}  {bar}")
        
        lines.append("")
    
    # So sánh với trung bình
    if vs_average_pct is not None:
        if vs_average_pct > 0:
            lines.append(f"So với trung bình: +{vs_average_pct:.0f}% ↑")
        elif vs_average_pct < 0:
            lines.append(f"So với trung bình: {vs_average_pct:.0f}% ↓")
        else:
            lines.append(f"So với trung bình: tương đương")
    
    return "\n".join(lines)


def format_budget_alert(
    category_code: str,
    spent: float,
    budget: float,
    days_left: int,
) -> str:
    """
    Cảnh báo khi gần/vượt ngân sách category.
    """
    cat = get_category(category_code)
    pct = (spent / budget * 100) if budget > 0 else 0
    
    if pct >= 100:
        emoji = "🚨"
        status = f"Đã vượt ngân sách {format_money_short(spent - budget)}"
    elif pct >= 90:
        emoji = "⚠️"
        status = f"Sắp chạm trần — còn {format_money_short(budget - spent)}"
    else:
        emoji = "📊"
        status = f"Còn {format_money_short(budget - spent)}"
    
    lines = [
        f"{emoji} Cảnh báo ngân sách",
        "",
        f"{cat.emoji} {cat.name_vi}",
        f"Đã chi: {format_money_short(spent)} / {format_money_short(budget)}",
        f"{make_progress_bar(spent, budget, width=10)}",
        "",
        status,
        f"Còn {days_left} ngày nữa hết tháng",
    ]
    
    return "\n".join(lines)


def format_welcome_message(display_name: str = None) -> str:
    """
    Tin nhắn chào đầu tiên khi user gõ /start.
    Phase 2 sẽ mở rộng thành full onboarding.
    """
    greeting = f"Chào {display_name}!" if display_name else "Chào bạn!"
    
    return f"""👋 {greeting}

Mình là trợ lý tài chính của bạn.
Mình không chỉ ghi chép — mình hiểu bạn.

Thử ngay nhé:
• Gõ "45k phở" để ghi giao dịch
• Gửi ảnh hóa đơn
• Gửi voice message

Hoặc tap /help để xem hướng dẫn đầy đủ 💪"""
```

### Test: `tests/test_templates.py`

```python
from datetime import datetime
from app.bot.formatters.templates import (
    format_transaction_confirmation,
    format_daily_summary,
)


def test_transaction_confirmation_basic():
    result = format_transaction_confirmation(
        merchant="Phở Bát Đàn",
        amount=45000,
        category_code="food",
    )
    assert "✅" in result
    assert "Phở Bát Đàn" in result
    assert "45,000đ" in result
    assert "🍜" in result  # Food emoji


def test_transaction_confirmation_with_budget():
    result = format_transaction_confirmation(
        merchant="Highlands",
        amount=85000,
        category_code="food",
        daily_spent=215000,
        daily_budget=400000,
    )
    assert "54%" in result  # 215/400 = 53.75 → 54%
    assert "Còn 185k" in result


def test_transaction_over_budget():
    result = format_transaction_confirmation(
        merchant="Lotte Mart",
        amount=500000,
        category_code="shopping",
        daily_spent=550000,
        daily_budget=400000,
    )
    assert "Vượt" in result or "Đã vượt" in result


def test_daily_summary():
    result = format_daily_summary(
        date=datetime(2025, 4, 15),
        total_spent=485000,
        transaction_count=4,
        breakdown=[
            ("food", 245000),
            ("transport", 150000),
            ("shopping", 90000),
        ],
        vs_average_pct=12,
    )
    assert "15/04" in result
    assert "485,000đ" in result
    assert "🍜 Ăn uống" in result
    assert "+12%" in result
```

---

## ✅ Checklist Cuối Tuần 1

- [ ] File `app/config/categories.py` — đầy đủ 13 categories với emoji + color
- [ ] File `app/bot/formatters/progress_bar.py` + tests pass
- [ ] File `app/bot/formatters/money.py` + tests pass
- [ ] File `app/bot/formatters/templates.py` — ít nhất 4 templates: transaction, daily summary, budget alert, welcome
- [ ] Replace TẤT CẢ `bot.send_message(..., "Đã lưu")` cũ bằng template mới
- [ ] Tự test trên Telegram: ghi 10 giao dịch, xem tin nhắn đẹp chưa

---

# 🎯 TUẦN 2: Inline Buttons Thông Minh

## 2.1 — Kiến Trúc Callback System

### File: `app/bot/keyboards/common.py`

Thiết kế callback_data theo convention rõ ràng để dễ route:

```python
"""
Callback data convention:
    <action>:<resource_id>[:<extra>]

Examples:
    edit_tx:123
    change_cat:123:food
    view_report:2025-04
    undo_tx:123
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


class CallbackPrefix:
    EDIT_TRANSACTION = "edit_tx"
    CHANGE_CATEGORY = "change_cat"
    DELETE_TRANSACTION = "del_tx"
    UNDO_TRANSACTION = "undo_tx"
    VIEW_REPORT = "view_report"
    SELECT_CATEGORY = "sel_cat"
    CONFIRM_ACTION = "confirm"
    CANCEL_ACTION = "cancel"


def parse_callback(data: str) -> tuple[str, list[str]]:
    """
    Parse callback_data thành (prefix, args).
    
    Examples:
        >>> parse_callback("edit_tx:123")
        ('edit_tx', ['123'])
        >>> parse_callback("change_cat:123:food")
        ('change_cat', ['123', 'food'])
    """
    parts = data.split(":")
    return parts[0], parts[1:]


def build_callback(prefix: str, *args) -> str:
    """Build callback string với validation độ dài."""
    data = ":".join([prefix, *[str(a) for a in args]])
    # Telegram giới hạn callback_data = 64 bytes
    if len(data.encode("utf-8")) > 64:
        raise ValueError(f"Callback data quá dài: {data}")
    return data
```

---

## 2.2 — Transaction Keyboards

### File: `app/bot/keyboards/transaction_keyboard.py`

```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from app.bot.keyboards.common import CallbackPrefix, build_callback
from app.config.categories import get_all_categories


def transaction_actions_keyboard(transaction_id: int) -> InlineKeyboardMarkup:
    """
    Keyboard xuất hiện SAU khi ghi giao dịch thành công.
    
    Layout:
    [🏷 Đổi danh mục] [✏️ Sửa số tiền] [🗑 Xóa]
    [↶ Hủy (5s)]
    """
    keyboard = [
        [
            InlineKeyboardButton(
                "🏷 Đổi danh mục",
                callback_data=build_callback(CallbackPrefix.CHANGE_CATEGORY, transaction_id)
            ),
            InlineKeyboardButton(
                "✏️ Sửa",
                callback_data=build_callback(CallbackPrefix.EDIT_TRANSACTION, transaction_id)
            ),
            InlineKeyboardButton(
                "🗑 Xóa",
                callback_data=build_callback(CallbackPrefix.DELETE_TRANSACTION, transaction_id)
            ),
        ],
        [
            InlineKeyboardButton(
                "↶ Hủy (5s)",
                callback_data=build_callback(CallbackPrefix.UNDO_TRANSACTION, transaction_id)
            ),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def category_picker_keyboard(transaction_id: int) -> InlineKeyboardMarkup:
    """
    Keyboard hiện list categories khi user tap "Đổi danh mục".
    
    Layout: 2 columns x 7 rows
    [🍜 Ăn uống]    [🚗 Di chuyển]
    [🏠 Nhà cửa]    [👕 Mua sắm]
    ...
    [❌ Hủy]
    """
    categories = get_all_categories()
    keyboard = []
    
    # Chia 2 cột
    for i in range(0, len(categories), 2):
        row = []
        for cat in categories[i:i+2]:
            row.append(
                InlineKeyboardButton(
                    f"{cat.emoji} {cat.name_vi}",
                    callback_data=build_callback(
                        CallbackPrefix.CHANGE_CATEGORY,
                        transaction_id,
                        cat.code
                    )
                )
            )
        keyboard.append(row)
    
    # Nút hủy
    keyboard.append([
        InlineKeyboardButton(
            "❌ Hủy",
            callback_data=build_callback(CallbackPrefix.CANCEL_ACTION)
        )
    ])
    
    return InlineKeyboardMarkup(keyboard)


def confirm_delete_keyboard(transaction_id: int) -> InlineKeyboardMarkup:
    """Xác nhận trước khi xóa giao dịch."""
    keyboard = [[
        InlineKeyboardButton(
            "✅ Xóa",
            callback_data=build_callback(
                CallbackPrefix.CONFIRM_ACTION,
                "delete",
                transaction_id
            )
        ),
        InlineKeyboardButton(
            "❌ Không",
            callback_data=build_callback(CallbackPrefix.CANCEL_ACTION)
        ),
    ]]
    return InlineKeyboardMarkup(keyboard)
```

---

## 2.3 — Callback Handler (Router)

### File: `app/bot/handlers/callbacks.py`

Đây là phần quan trọng nhất — xử lý mọi button tap.

```python
"""
Central callback handler.
Route callback_data tới handler phù hợp.
"""

from telegram import Update
from telegram.ext import ContextTypes
from app.bot.keyboards.common import parse_callback, CallbackPrefix
from app.bot.keyboards.transaction_keyboard import (
    category_picker_keyboard,
    confirm_delete_keyboard,
    transaction_actions_keyboard,
)
from app.bot.formatters.templates import format_transaction_confirmation
from app.services.transaction_service import TransactionService
from app.config.categories import get_category


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main callback router.
    Mọi button tap đều vào đây, rồi phân phối.
    """
    query = update.callback_query
    await query.answer()  # Dismiss "loading" indicator ngay
    
    prefix, args = parse_callback(query.data)
    user_id = query.from_user.id
    
    # Route tới handler phù hợp
    handlers = {
        CallbackPrefix.CHANGE_CATEGORY: handle_change_category,
        CallbackPrefix.DELETE_TRANSACTION: handle_delete_transaction,
        CallbackPrefix.CONFIRM_ACTION: handle_confirm_action,
        CallbackPrefix.CANCEL_ACTION: handle_cancel_action,
        CallbackPrefix.UNDO_TRANSACTION: handle_undo_transaction,
    }
    
    handler = handlers.get(prefix)
    if not handler:
        await query.edit_message_text("❌ Action không hợp lệ")
        return
    
    await handler(update, context, args, user_id)


async def handle_change_category(update, context, args, user_id):
    """
    Flow đổi category:
    1. User tap "Đổi danh mục" → args = [tx_id] → hiện category picker
    2. User tap category → args = [tx_id, cat_code] → update DB + edit message
    """
    query = update.callback_query
    transaction_id = int(args[0])
    
    if len(args) == 1:
        # Step 1: Hiện picker
        await query.edit_message_reply_markup(
            reply_markup=category_picker_keyboard(transaction_id)
        )
    else:
        # Step 2: Đã chọn category
        new_category = args[1]
        service = TransactionService()
        
        transaction = await service.update_category(
            transaction_id=transaction_id,
            user_id=user_id,
            new_category=new_category,
        )
        
        # Edit lại message gốc với thông tin mới
        new_text = format_transaction_confirmation(
            merchant=transaction.merchant,
            amount=transaction.amount,
            category_code=new_category,
            location=transaction.location,
            time=transaction.transaction_time,
            daily_spent=await service.get_daily_spent(user_id),
            daily_budget=await service.get_daily_budget(user_id),
        )
        
        await query.edit_message_text(
            text=new_text,
            reply_markup=transaction_actions_keyboard(transaction_id)
        )


async def handle_delete_transaction(update, context, args, user_id):
    """Hỏi xác nhận trước khi xóa."""
    query = update.callback_query
    transaction_id = int(args[0])
    
    await query.edit_message_reply_markup(
        reply_markup=confirm_delete_keyboard(transaction_id)
    )


async def handle_confirm_action(update, context, args, user_id):
    """Xử lý confirm cho các actions nhạy cảm (delete, ...)."""
    query = update.callback_query
    action_type = args[0]
    
    if action_type == "delete":
        transaction_id = int(args[1])
        service = TransactionService()
        await service.delete_transaction(transaction_id, user_id)
        
        await query.edit_message_text("🗑 Đã xóa giao dịch")


async def handle_cancel_action(update, context, args, user_id):
    """User hủy action, quay lại keyboard ban đầu."""
    query = update.callback_query
    # Lấy transaction_id từ message context (cần lưu state hoặc parse message)
    # Đơn giản nhất: edit message về trạng thái ban đầu
    await query.edit_message_reply_markup(reply_markup=None)


async def handle_undo_transaction(update, context, args, user_id):
    """Undo giao dịch vừa ghi (chỉ trong 5s đầu)."""
    query = update.callback_query
    transaction_id = int(args[0])
    
    service = TransactionService()
    success = await service.undo_recent_transaction(
        transaction_id=transaction_id,
        user_id=user_id,
        max_age_seconds=5,
    )
    
    if success:
        await query.edit_message_text("↶ Đã hủy giao dịch")
    else:
        await query.answer("Quá muộn để hủy — dùng nút 🗑 Xóa nhé", show_alert=True)
```

---

## 2.4 — Cập Nhật Transaction Handler

### File: `app/bot/handlers/transaction.py` (update)

Khi ghi giao dịch mới, attach keyboard:

```python
from app.bot.keyboards.transaction_keyboard import transaction_actions_keyboard
from app.bot.formatters.templates import format_transaction_confirmation


async def handle_new_transaction(update, context, parsed_data):
    """
    Sau khi parse được giao dịch, lưu DB + gửi confirmation đẹp.
    """
    service = TransactionService()
    user_id = update.effective_user.id
    
    # Lưu DB
    transaction = await service.create_transaction(user_id=user_id, **parsed_data)
    
    # Lấy context cho tin nhắn
    daily_spent = await service.get_daily_spent(user_id)
    daily_budget = await service.get_daily_budget(user_id)
    
    # Format message
    text = format_transaction_confirmation(
        merchant=transaction.merchant,
        amount=transaction.amount,
        category_code=transaction.category_code,
        location=transaction.location,
        time=transaction.transaction_time,
        daily_spent=daily_spent,
        daily_budget=daily_budget,
    )
    
    # Gửi với keyboard
    await update.message.reply_text(
        text=text,
        reply_markup=transaction_actions_keyboard(transaction.id),
    )
```

---

## ✅ Checklist Cuối Tuần 2

- [ ] File `keyboards/common.py` — callback convention + parser
- [ ] File `keyboards/transaction_keyboard.py` — 3 keyboards
- [ ] File `handlers/callbacks.py` — router + 5 handlers
- [ ] Transaction handler gắn keyboard sau mỗi giao dịch
- [ ] Test manual: ghi giao dịch → tap từng button → verify hoạt động đúng
- [ ] Tests unit cho callback parser

---

# 💎 TUẦN 3: Telegram Mini App (Dashboard v1)

## 3.1 — Setup Mini App Trong BotFather

### Các bước thủ công:

1. Mở BotFather trên Telegram
2. Gõ `/mybots` → chọn bot của bạn
3. `Bot Settings` → `Menu Button` → `Edit menu button URL`
4. Nhập URL: `https://your-domain.com/miniapp/dashboard`
5. Label: `📊 Dashboard`

**Yêu cầu:** Domain PHẢI có HTTPS. Trong dev:
- Dùng `ngrok` để expose localhost: `ngrok http 8000`
- Hoặc Cloudflare Tunnel (miễn phí)
- Production: Let's Encrypt trên VPS

---

## 3.2 — Mini App Authentication

### File: `app/miniapp/auth.py`

Telegram gửi `initData` khi user mở Mini App — verify HMAC để xác thực.

```python
"""
Verify Telegram Mini App initData.
Docs: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hmac
import hashlib
from urllib.parse import unquote, parse_qsl
from app.config import settings


def verify_init_data(init_data: str) -> dict | None:
    """
    Verify initData từ Telegram Mini App.
    
    Returns:
        Dict chứa user info nếu valid, None nếu invalid.
    
    Raises:
        ValueError nếu format sai.
    """
    try:
        # Parse query string
        parsed = dict(parse_qsl(init_data))
        received_hash = parsed.pop("hash")
        
        # Tạo data-check-string
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )
        
        # Tạo secret key từ bot token
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=settings.TELEGRAM_BOT_TOKEN.encode(),
            digestmod=hashlib.sha256,
        ).digest()
        
        # Compute expected hash
        expected_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()
        
        # Compare
        if hmac.compare_digest(received_hash, expected_hash):
            # Parse user info
            import json
            user_json = parsed.get("user", "{}")
            user = json.loads(unquote(user_json))
            return {
                "user_id": user.get("id"),
                "first_name": user.get("first_name"),
                "username": user.get("username"),
                "auth_date": int(parsed.get("auth_date", 0)),
            }
        return None
    except Exception as e:
        print(f"Auth error: {e}")
        return None


# FastAPI dependency
from fastapi import Header, HTTPException


async def require_miniapp_auth(
    x_telegram_init_data: str = Header(..., alias="X-Telegram-Init-Data")
):
    """
    FastAPI dependency — verify request từ Mini App.
    Mini App phải gửi header X-Telegram-Init-Data với mọi API call.
    """
    user_data = verify_init_data(x_telegram_init_data)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid Telegram auth")
    return user_data
```

---

## 3.3 — Mini App Routes

### File: `app/miniapp/routes.py`

```python
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.miniapp.auth import require_miniapp_auth
from app.services.report_service import ReportService


router = APIRouter(prefix="/miniapp", tags=["miniapp"])
templates = Jinja2Templates(directory="app/miniapp/templates")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Serve HTML page — không require auth (auth check ở API level)."""
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request}
    )


# ===== API endpoints cho Mini App gọi =====

@router.get("/api/overview")
async def get_overview(auth = Depends(require_miniapp_auth)):
    """
    Trả về số liệu tổng quan cho dashboard.
    Response:
    {
        "month": "2025-04",
        "total_spent": 8500000,
        "transaction_count": 45,
        "top_categories": [
            {"code": "food", "name": "Ăn uống", "emoji": "🍜", "amount": 3200000, "color": "#FF6B6B"},
            ...
        ],
        "daily_trend": [
            {"date": "2025-04-01", "amount": 285000},
            ...
        ]
    }
    """
    user_id = auth["user_id"]
    service = ReportService()
    
    return {
        "month": await service.current_month(),
        "total_spent": await service.get_month_total(user_id),
        "transaction_count": await service.get_month_transaction_count(user_id),
        "top_categories": await service.get_category_breakdown(user_id),
        "daily_trend": await service.get_daily_trend(user_id, days=30),
    }


@router.get("/api/recent-transactions")
async def get_recent(
    limit: int = 20,
    auth = Depends(require_miniapp_auth)
):
    """List giao dịch gần đây."""
    service = ReportService()
    return await service.get_recent_transactions(auth["user_id"], limit=limit)
```

---

## 3.4 — Mini App Frontend

### File: `app/miniapp/templates/dashboard.html`

```html
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <link rel="stylesheet" href="/static/miniapp/css/style.css">
</head>
<body>
    <div id="app">
        <!-- Loading state -->
        <div id="loading" class="loading">
            <div class="spinner"></div>
            <p>Đang tải...</p>
        </div>
        
        <!-- Main content -->
        <div id="content" style="display: none;">
            <!-- Header card -->
            <div class="card card-primary">
                <div class="card-label">Chi tiêu tháng này</div>
                <div class="card-amount" id="total-spent">—</div>
                <div class="card-meta">
                    <span id="transaction-count">—</span> giao dịch
                </div>
            </div>
            
            <!-- Category breakdown -->
            <div class="section">
                <h2>Theo danh mục</h2>
                <div class="chart-container">
                    <canvas id="category-chart"></canvas>
                </div>
                <div id="category-list"></div>
            </div>
            
            <!-- Daily trend -->
            <div class="section">
                <h2>Xu hướng 30 ngày</h2>
                <div class="chart-container">
                    <canvas id="trend-chart"></canvas>
                </div>
            </div>
        </div>
    </div>
    
    <script src="/static/miniapp/js/dashboard.js"></script>
</body>
</html>
```

### File: `app/miniapp/static/js/dashboard.js`

```javascript
// Initialize Telegram Web App
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

// Apply Telegram theme
document.documentElement.style.setProperty('--bg-color', tg.themeParams.bg_color || '#ffffff');
document.documentElement.style.setProperty('--text-color', tg.themeParams.text_color || '#000000');

// Format money helper
function formatMoney(amount) {
    if (amount >= 1_000_000) {
        return (amount / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'tr';
    }
    if (amount >= 1000) {
        return Math.round(amount / 1000) + 'k';
    }
    return amount + 'đ';
}

// Fetch data from API
async function fetchAPI(endpoint) {
    const response = await fetch(`/miniapp/api${endpoint}`, {
        headers: {
            'X-Telegram-Init-Data': tg.initData,
        },
    });
    if (!response.ok) throw new Error('API error');
    return response.json();
}

// Render overview
async function renderDashboard() {
    try {
        const data = await fetchAPI('/overview');
        
        // Total spent
        document.getElementById('total-spent').textContent = 
            new Intl.NumberFormat('vi-VN').format(data.total_spent) + 'đ';
        document.getElementById('transaction-count').textContent = data.transaction_count;
        
        // Category pie chart
        renderCategoryChart(data.top_categories);
        renderCategoryList(data.top_categories);
        
        // Daily trend line chart
        renderTrendChart(data.daily_trend);
        
        // Show content, hide loading
        document.getElementById('loading').style.display = 'none';
        document.getElementById('content').style.display = 'block';
    } catch (error) {
        console.error(error);
        tg.showAlert('Không tải được dữ liệu. Vui lòng thử lại.');
    }
}

function renderCategoryChart(categories) {
    const ctx = document.getElementById('category-chart').getContext('2d');
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: categories.map(c => c.name),
            datasets: [{
                data: categories.map(c => c.amount),
                backgroundColor: categories.map(c => c.color),
                borderWidth: 0,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
            },
        },
    });
}

function renderCategoryList(categories) {
    const container = document.getElementById('category-list');
    const maxAmount = Math.max(...categories.map(c => c.amount));
    
    container.innerHTML = categories.map(cat => `
        <div class="category-row">
            <div class="category-info">
                <span class="emoji">${cat.emoji}</span>
                <span class="name">${cat.name}</span>
            </div>
            <div class="category-bar-wrap">
                <div class="category-bar" style="width: ${(cat.amount/maxAmount*100)}%; background: ${cat.color}"></div>
            </div>
            <div class="category-amount">${formatMoney(cat.amount)}</div>
        </div>
    `).join('');
}

function renderTrendChart(dailyData) {
    const ctx = document.getElementById('trend-chart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: dailyData.map(d => d.date.slice(5)),  // MM-DD
            datasets: [{
                data: dailyData.map(d => d.amount),
                borderColor: '#4ECDC4',
                backgroundColor: 'rgba(78, 205, 196, 0.1)',
                fill: true,
                tension: 0.3,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: {
                    ticks: { callback: v => formatMoney(v) },
                },
            },
        },
    });
}

// Kick off
renderDashboard();
```

### File: `app/miniapp/static/css/style.css`

```css
:root {
    --bg-color: #f5f7fa;
    --card-bg: #ffffff;
    --text-color: #1a1a1a;
    --text-muted: #8a8a8a;
    --primary: #4ECDC4;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg-color);
    color: var(--text-color);
    padding: 16px;
}

.card {
    background: var(--card-bg);
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

.card-primary {
    background: linear-gradient(135deg, #4ECDC4 0%, #44A08D 100%);
    color: white;
}

.card-label {
    font-size: 13px;
    opacity: 0.9;
    margin-bottom: 8px;
}

.card-amount {
    font-size: 32px;
    font-weight: 700;
    margin-bottom: 4px;
}

.card-meta {
    font-size: 13px;
    opacity: 0.9;
}

.section {
    background: var(--card-bg);
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 16px;
}

.section h2 {
    font-size: 16px;
    margin-bottom: 16px;
}

.chart-container {
    position: relative;
    height: 200px;
    margin-bottom: 16px;
}

.category-row {
    display: grid;
    grid-template-columns: 120px 1fr 60px;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
}

.category-info .emoji {
    margin-right: 6px;
}

.category-bar-wrap {
    height: 8px;
    background: #f0f0f0;
    border-radius: 4px;
    overflow: hidden;
}

.category-bar {
    height: 100%;
    border-radius: 4px;
    transition: width 0.5s ease;
}

.category-amount {
    text-align: right;
    font-size: 13px;
    font-weight: 600;
}

.loading {
    text-align: center;
    padding: 80px 20px;
}

.spinner {
    width: 40px;
    height: 40px;
    border: 3px solid #eee;
    border-top-color: var(--primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto 16px;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}
```

---

## ✅ Checklist Cuối Tuần 3

- [ ] Đăng ký Mini App URL trong BotFather
- [ ] File `miniapp/auth.py` — verify initData
- [ ] File `miniapp/routes.py` — 2 API endpoints
- [ ] File `dashboard.html` + `dashboard.js` + `style.css`
- [ ] Test trên thiết bị thật (không chỉ desktop): iPhone + Android
- [ ] Dashboard load <1.5s
- [ ] Chart render đẹp, responsive

---

# 🎨 TUẦN 4: Visual Identity + Polish

## 4.1 — Chọn Tên & Mascot

### Công việc:

- [ ] **Brainstorm 5 tên bot**, chọn 1:
  - Gợi ý: Xu, Tiết, Dư, Chi, Bông, Finny, Tiny
  - Tiêu chí: ngắn, dễ nhớ, thân thiện, không xung đột trademark VN
  
- [ ] **Thuê mascot** hoặc tự tạo:
  - Option A: Fiverr ($50-100) — search "chibi mascot finance"
  - Option B: Midjourney prompt: `cute chibi mascot, piggy bank character, friendly smile, minimalist vector style, vietnamese finance app, 3 expressions: happy, worried, surprised`
  - Yêu cầu 3 expressions (happy, worried, celebrating)

- [ ] **Tạo bot profile picture** 512x512, background trắng sạch

- [ ] **Cập nhật bio bot** trong BotFather:
  ```
  /setdescription
  Trợ lý tài chính cá nhân thông minh — ghi chép nhanh, hiểu bạn sâu 💚
  ```

---

## 4.2 — Tone Writing Guide

### File: `docs/tone_guide.md`

Tạo tài liệu nội bộ làm kim chỉ nam:

```markdown
# Tone Writing Guide

## Xưng hô
- Bot xưng "mình"
- Gọi user bằng "bạn" hoặc tên user đã nhập

## Nguyên tắc cơ bản
- NGẮN GỌN: 1 ý 1 dòng, có khoảng trắng giữa các ý
- ẤM ÁP: như bạn bè, không như ngân hàng
- KHÔNG PHÁN XÉT: tránh từ "sai", "lãng phí", "tệ"
- CÓ CHOICE: đưa lựa chọn, không ra lệnh

## Bảng từ tránh → thay thế

| Tránh              | Thay bằng                    |
|--------------------|------------------------------|
| Bạn đã tiêu quá    | Mình để ý thấy tháng này...  |
| Đừng mua           | Có thể cân nhắc...           |
| Sai rồi            | Hmm, mình chưa hiểu lắm      |
| Vui lòng           | (bỏ, không cần)              |
| Hệ thống đã lưu    | Ghi xong rồi!                |

## Emoji guide
- Tích cực: ✅ 🎉 🌱 💪 👌
- Trung tính: 📊 💰 📌
- Lo lắng nhẹ: 🫣 😅 ⚠️
- KHÔNG dùng: 💀 🤬 ❌ (trừ khi thực sự cần)
```

---

## 4.3 — Polish Các Tin Nhắn Cũ

- [ ] Review toàn bộ tin nhắn bot đang gửi
- [ ] Áp dụng tone guide
- [ ] Test với 3-5 bạn bè, thu feedback về "cảm giác"

---

## 4.4 — Friends Beta Testing

### Checklist test:

- [ ] Gửi link bot cho 5-10 friends
- [ ] Tạo Google Form feedback ngắn (5 câu):
  1. Tin nhắn bot có đẹp không? (1-5)
  2. Thao tác có dễ không? (1-5)
  3. Bot có "dễ thương" không? (1-5)
  4. Có gì khó chịu nhất?
  5. Nếu được thêm 1 thứ, bạn muốn gì?
- [ ] Phỏng vấn 2-3 người qua video call
- [ ] Tổng hợp insights → quyết định fix trước khi sang Phase 2

---

# 📊 Metrics Cần Track Từ Phase 1

Setup analytics ngay tuần 1:

```python
# app/analytics.py
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Event:
    user_id: int
    event_type: str  # "transaction_created", "button_tapped", "miniapp_opened", ...
    properties: dict
    timestamp: datetime


async def track(event: Event):
    """Lưu vào bảng events trong DB hoặc gửi tới Mixpanel/PostHog."""
    # Đơn giản nhất: lưu PostgreSQL
    pass
```

**Track các events:**
- `/start` — bot opened
- `transaction_created` (source: text/voice/image)
- `button_tapped` (which button)
- `miniapp_opened`
- `miniapp_loaded` (với load time)
- `category_changed`
- `transaction_deleted`

**Review weekly:** Button nào được dùng nhiều? Mini App load có nhanh không? Có lỗi gì không?

---

# 🎯 Exit Criteria Của Phase 1

Chỉ chuyển sang Phase 2 khi **TẤT CẢ** checklist sau đạt:

- [ ] Mọi tin nhắn bot gửi đều dùng template đẹp (không còn text khô)
- [ ] Mọi giao dịch đều có inline buttons (edit, delete, category)
- [ ] Mini App mở được, load <2s, hiển thị đúng data
- [ ] Bot có tên + mascot + tone writing nhất quán
- [ ] Ít nhất 5 friends đã test và cho feedback
- [ ] Bug list được ghi lại, các bug critical đã fix
- [ ] Analytics hoạt động, có data 1 tuần để review

**Nếu 1 trong các điều kiện trên chưa đạt → ở lại Phase 1 thêm 1 tuần.** Đừng vội chuyển Phase — nền móng không chắc thì mọi thứ xây lên trên sẽ đổ.

---

# 🚧 Bẫy Thường Gặp (Tránh!)

1. **Over-engineer sớm**: Đừng xây abstraction layer quá deep cho Phase 1. Code đơn giản, dễ sửa.

2. **Bỏ qua tests**: Ít nhất phải có test cho `progress_bar`, `money formatter`, `callback parser` — 3 thứ này có bug là tin nhắn hiển thị sai.

3. **Mini App quá phức tạp**: Phase 1 chỉ cần dashboard đơn giản. Đừng cố build full SPA với routing.

4. **Không test trên mobile thật**: Mini App trên desktop trông khác mobile rất nhiều. PHẢI test iPhone + Android.

5. **Bỏ qua emoji compatibility**: Một số emoji mới không render trên Android cũ. Dùng emoji cổ điển, an toàn.

6. **Callback data quá dài**: Telegram giới hạn 64 bytes. Dùng ID thay vì string dài.

---

# 📚 Tài Liệu Tham Khảo

- Telegram Bot API: https://core.telegram.org/bots/api
- Telegram Mini Apps: https://core.telegram.org/bots/webapps
- python-telegram-bot docs: https://docs.python-telegram-bot.org/
- Chart.js: https://www.chartjs.org/docs/latest/

---

# 🎉 Next Step

Khi Phase 1 đã "Done", tạo file `phase-2-detailed.md` với nội dung:
- Onboarding 3 phút (state machine chi tiết)
- Memory moments (schema + scheduled jobs)
- Empathy triggers (rules engine)
- Seasonal content calendar cho 12 tháng

**Good luck với Phase 1! 💚**
