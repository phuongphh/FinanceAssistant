# Phase 3 — Zero-Input Philosophy (Chi Tiết Triển Khai)

> **Thời gian ước tính:** 5-6 tuần (có thể dài hơn Phase 1+2 cộng lại — đừng vội)
> **Mục tiêu cuối Phase:** 90% giao dịch tự capture không cần nhập tay. User chỉ verify/sửa khi cần, thao tác tối đa 1-2 giây.
> **Điều kiện "Done":** Một user Android điển hình (VN, dùng 2 bank + MoMo) chỉ nhập tay <10% giao dịch. User iPhone chỉ nhập tay <25%.

> **Prerequisites:** Phase 1 (rich UX) và Phase 2 (personality) đã stable. User đã trust bot — đây là điều kiện tiên quyết để họ forward SMS ngân hàng (thông tin cực nhạy cảm).

---

## 🎯 Quyết Định Thiết Kế Quan Trọng (Đọc Trước Khi Code)

Trước khi vào chi tiết, tôi muốn chia sẻ 3 quyết định thiết kế đã nghĩ kỹ và khác với strategy gốc:

### 1. Thứ tự triển khai thay đổi

Strategy gốc: SMS → OCR → Voice → Location → Wrap-up.

**Thứ tự đề xuất mới:** Daily Wrap-up (Tuần 1) → SMS (Tuần 2-3) → OCR (Tuần 4) → Voice (Tuần 5) → Location (Tuần 6, optional).

**Lý do:**
- **Wrap-up trước vì đây là safety net** — làm xong ngay 1 tuần có giá trị lập tức, không phụ thuộc tầng nào
- Wrap-up giúp **discover** giao dịch nào user quên nhiều nhất → hiểu ưu tiên thật
- SMS là giá trị cao nhất nhưng risk cao nhất (privacy) — cần foundation stable (Tuần 1) trước

### 2. "Conversational Correction" là trung tâm, không phải "perfect parsing"

Sẽ không bao giờ parse 100% đúng. Thay vì ám ảnh độ chính xác, **tối ưu flow sửa sai**:
- Mỗi giao dịch auto-capture đều có inline buttons để sửa trong 1 tap
- Bot **hỏi khi không chắc** thay vì đoán bừa
- User sửa = signal để learn, không phải failure

### 3. Learning Loop là heart của hệ thống

Categorizer phải **học từ mỗi lần user sửa**. Sau 3 tháng, bot của user quen thuộc sẽ chính xác >95%. Sau 6 tháng, gần 100%.

Đây là lợi thế cạnh tranh thực sự — MISA/Money Lover không có khái niệm này.

### 4. iPhone Strategy phải được plan từ đầu

30-40% user target của bạn dùng iPhone. SMS Forward không work trên iOS. **Giải pháp cho iPhone:**
- Shortcuts app của Apple (tự động hóa được nhiều)
- Screenshot OCR mạnh hơn (bù lại)
- Email forwarding (nhiều bank VN có option gửi email giao dịch)
- Active wrap-up hỏi nhiều hơn

---

## 📅 Phân Bổ Thời Gian 6 Tuần

| Tuần | Nội dung chính | Deliverable |
|------|---------------|-------------|
| **Tuần 1** | Daily Wrap-up + Conversational Input | Bot hỏi cuối ngày, user bổ sung bằng chat tự do |
| **Tuần 2** | SMS Parsers (top 5 banks) | Parse 95%+ SMS của VCB, Techcom, MB, ACB, VPBank |
| **Tuần 3** | SMS Integration + Forwarder Guide | User setup được auto-forward, giao dịch vào DB |
| **Tuần 4** | Screenshot OCR (Claude Vision) | MoMo/ZaloPay/bank app screenshots auto-parse |
| **Tuần 5** | Voice Input + Smart Categorizer | Voice → transcript → parse; categorizer học được |
| **Tuần 6** | Location Capture (opt-in) + Polish + Metrics | Tầng 5 optional, đo tỉ lệ tự động, iterate |

**Lưu ý:** Nếu tuần nào bị deadline khít, **ưu tiên dừng ở Tuần 4**. SMS + Wrap-up + OCR đã đủ cho 85% giao dịch. Voice và Location có thể để Phase 3.5.

---

# 🗂️ Cấu Trúc Thư Mục Mở Rộng

```
finance_assistant/
├── app/
│   ├── bot/
│   │   ├── handlers/
│   │   │   ├── sms_forward.py          # ⭐ NEW
│   │   │   ├── screenshot.py           # ⭐ NEW
│   │   │   ├── voice.py                # ⭐ NEW
│   │   │   ├── wrap_up.py              # ⭐ NEW
│   │   │   └── ...
│   │   ├── formatters/
│   │   │   └── capture_templates.py    # ⭐ NEW
│   │   └── keyboards/
│   │       ├── correction_keyboard.py  # ⭐ NEW
│   │       └── wrap_up_keyboard.py     # ⭐ NEW
│   │
│   ├── capture/                        # ⭐ NEW - Core của Phase 3
│   │   ├── __init__.py
│   │   ├── sms_parsers/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                 # Parser interface
│   │   │   ├── vcb.py
│   │   │   ├── techcombank.py
│   │   │   ├── mb.py
│   │   │   ├── acb.py
│   │   │   ├── vpbank.py
│   │   │   ├── registry.py             # Auto-detect bank
│   │   │   └── fixtures/               # Sample SMS for testing
│   │   │       ├── vcb_samples.txt
│   │   │       └── ...
│   │   ├── ocr/
│   │   │   ├── vision_client.py        # Claude Vision wrapper
│   │   │   ├── prompts.py              # OCR prompts
│   │   │   └── cache.py                # Hash-based cache
│   │   ├── voice/
│   │   │   ├── whisper_client.py
│   │   │   ├── nlu_parser.py           # "45k phở" → structured
│   │   │   └── context_resolver.py     # "như hôm qua"
│   │   └── location/
│   │       ├── places_client.py
│   │       └── commercial_detector.py
│   │
│   ├── categorizer/                    # ⭐ NEW - Smart categorizer
│   │   ├── __init__.py
│   │   ├── rule_engine.py              # Rule-based first
│   │   ├── llm_fallback.py             # DeepSeek fallback
│   │   ├── learning.py                 # Learn from corrections
│   │   └── rules.yaml                  # Rule definitions
│   │
│   ├── models/
│   │   ├── raw_sms.py                  # ⭐ NEW - Audit log
│   │   ├── merchant_rule.py            # ⭐ NEW - Learned rules
│   │   ├── parse_failure.py            # ⭐ NEW - Track failures
│   │   └── transaction.py              # Update: source, confidence
│   │
│   ├── services/
│   │   ├── capture_service.py          # ⭐ NEW - Unified capture API
│   │   ├── wrap_up_service.py          # ⭐ NEW
│   │   └── learning_service.py         # ⭐ NEW
│   │
│   ├── scheduled/
│   │   └── daily_wrap_up.py            # ⭐ NEW - Run 20:30 mỗi ngày
│   │
│   └── security/                       # ⭐ NEW - Phase 3 cần security tier
│       ├── encryption.py               # Encrypt sensitive fields
│       └── audit_log.py
│
├── content/
│   ├── forwarder_guides/               # ⭐ NEW
│   │   ├── vcb_android.md
│   │   ├── techcom_android.md
│   │   ├── iphone_shortcuts.md         # iPhone alternative
│   │   └── ...
│   └── wrap_up_prompts.yaml            # ⭐ NEW
│
└── tests/
    ├── test_sms_parsers/
    │   ├── test_vcb.py
    │   ├── test_techcombank.py
    │   └── ...
    ├── test_categorizer.py
    └── test_ocr.py
```

---

# 📦 TUẦN 1: Daily Wrap-up (Làm Đầu Tiên!)

> **Tại sao tuần 1:** Wrap-up là safety net hoạt động ngay với zero integration. Nó cũng là **tool discovery** — giúp bạn hiểu user quên gì, từ đó ưu tiên đúng cho tuần 2-6.

## 1.1 — Database: Transaction Sources

### Migration: thêm source tracking

```python
# alembic/versions/xxx_add_transaction_source.py
def upgrade():
    op.add_column('transactions', sa.Column('source', sa.String(20), default='manual'))
    op.add_column('transactions', sa.Column('confidence', sa.Float, default=1.0))
    op.add_column('transactions', sa.Column('raw_input', sa.Text, nullable=True))
    op.add_column('transactions', sa.Column('verified_by_user', sa.Boolean, default=False))
    
    # Index để query theo source (analytics)
    op.create_index('idx_transactions_source', 'transactions', ['user_id', 'source'])


# Source types:
# - "manual" — user gõ text
# - "sms" — parsed từ SMS forward
# - "ocr" — parsed từ screenshot
# - "voice" — parsed từ voice message
# - "location" — prompted từ location
# - "wrap_up" — ghi trong wrap-up conversation
```

### File: `app/models/transaction.py` (update)

```python
class TransactionSource(str, Enum):
    MANUAL = "manual"
    SMS = "sms"
    OCR = "ocr"
    VOICE = "voice"
    LOCATION = "location"
    WRAP_UP = "wrap_up"


class Transaction(Base):
    # ... existing columns ...
    source = Column(String(20), default=TransactionSource.MANUAL)
    confidence = Column(Float, default=1.0)  # 0.0-1.0
    raw_input = Column(Text, nullable=True)  # Preserve original input
    verified_by_user = Column(Boolean, default=False)
```

**Tại sao `confidence`:** Các giao dịch auto-captured (OCR, voice) sẽ có confidence thấp hơn manual. Khi render, ta sẽ hiển thị UI khác cho giao dịch low-confidence.

**Tại sao `raw_input`:** Khi parse sai, ta có context để debug. Khi user sửa, ta có "before/after" để learn.

---

## 1.2 — Wrap-up Content

### File: `content/wrap_up_prompts.yaml`

```yaml
# Các variant tin nhắn wrap-up cuối ngày

normal_day:
  - |
    🌙 Tóm tắt ngày {date_str}:
    
    {transaction_list}
    
    Tổng: {total}
    
    Có giao dịch nào mình bỏ sót không?

with_many_transactions:
  - |
    🌙 Hôm nay ngày {date_str}, bạn đã có {count} giao dịch:
    
    {transaction_list}
    
    Tổng: {total}
    
    Kiểm tra giúp mình xem đủ chưa nhé?

empty_day:
  - |
    🌙 Hôm nay {date_str} bạn chưa ghi giao dịch nào.
    
    Có phải bạn không chi tiêu gì, hay quên ghi? 😊

high_spending_day:
  - |
    🌙 {date_str} khá "mặn" đấy {name}!
    
    {transaction_list}
    
    Tổng: {total} — nhiều hơn {pct}% so với trung bình của bạn.
    
    Có gì đặc biệt hôm nay không? Hay có khoản nào mình ghi nhầm?

followup_incomplete:
  - "Kể cho mình nghe {name} đã chi gì thêm? Gõ ngắn cũng được, ví dụ 'cafe 45k' 💬"
  - "Còn khoản nào nữa? Mình sẽ ghi giúp bạn 📝"

followup_more:
  - "Ghi rồi! Còn gì nữa không? (Gõ 'xong' khi hết nhé)"
  - "Tuyệt! Còn khoản nào không?"

completion:
  - "✅ Tuyệt vời! Đã xong hết rồi. Ngủ ngon nhé {name} 💚"
  - "👌 Đầy đủ rồi! Mai gặp lại bạn nhé"
```

---

## 1.3 — Wrap-up Service

### File: `app/services/wrap_up_service.py`

```python
"""
Wrap-up service — quản lý conversation cuối ngày.

Flow:
1. Scheduled 20:30 (adaptive) → gửi summary + hỏi "thiếu gì không?"
2. User tap "Bổ sung" → bot bật "wrap_up mode"
3. Trong wrap_up mode: mỗi text message = 1 giao dịch, parse và confirm
4. User gõ "xong"/"hết"/"đủ rồi" → thoát mode
5. Timeout sau 15 phút không reply → tự động thoát
"""

import random
import yaml
from datetime import datetime, time, timedelta
from pathlib import Path

from app.services.transaction_service import TransactionService
from app.bot.formatters.money import format_money_full, format_money_short
from app.bot.formatters.templates import format_transaction_line


class WrapUpService:
    WRAP_UP_MODE_TIMEOUT_MINUTES = 15
    
    def __init__(self):
        self._prompts = self._load_prompts()
    
    def _load_prompts(self):
        with open("content/wrap_up_prompts.yaml") as f:
            return yaml.safe_load(f)
    
    async def generate_summary(self, user) -> str:
        """Tạo tin nhắn wrap-up dựa trên ngày của user."""
        today = datetime.utcnow().date()
        tx_service = TransactionService()
        
        transactions = await tx_service.get_transactions_by_date(user.id, today)
        
        if not transactions:
            template = random.choice(self._prompts["empty_day"])
            return template.format(
                date_str=today.strftime("%d/%m"),
                name=user.display_name or "bạn",
            )
        
        # Format transaction list
        tx_list = "\n".join([
            f"✓ {tx.merchant} {format_money_short(tx.amount)} ({self._source_label(tx.source)})"
            for tx in transactions
        ])
        total = sum(tx.amount for tx in transactions)
        
        # Check nếu là high spending day
        avg = await tx_service.get_daily_average(user.id, days=30)
        
        context = {
            "date_str": today.strftime("%d/%m"),
            "name": user.display_name or "bạn",
            "transaction_list": tx_list,
            "total": format_money_full(total),
            "count": len(transactions),
        }
        
        if avg > 0 and total > avg * 1.5:
            context["pct"] = int((total / avg - 1) * 100)
            template = random.choice(self._prompts["high_spending_day"])
        elif len(transactions) >= 5:
            template = random.choice(self._prompts["with_many_transactions"])
        else:
            template = random.choice(self._prompts["normal_day"])
        
        return template.format(**context)
    
    def _source_label(self, source: str) -> str:
        labels = {
            "manual": "bạn ghi",
            "sms": "từ SMS",
            "ocr": "từ ảnh",
            "voice": "từ voice",
            "location": "từ location",
            "wrap_up": "tối qua",
        }
        return labels.get(source, "")
    
    async def enter_wrap_up_mode(self, user_id: int):
        """Đánh dấu user đang trong wrap_up mode."""
        # Lưu state trong Redis hoặc DB (TTL 15 phút)
        from app.cache import cache
        await cache.set(
            f"wrap_up_mode:{user_id}",
            "active",
            expire=self.WRAP_UP_MODE_TIMEOUT_MINUTES * 60,
        )
    
    async def exit_wrap_up_mode(self, user_id: int):
        from app.cache import cache
        await cache.delete(f"wrap_up_mode:{user_id}")
    
    async def is_in_wrap_up_mode(self, user_id: int) -> bool:
        from app.cache import cache
        return await cache.exists(f"wrap_up_mode:{user_id}")
    
    def is_exit_keyword(self, text: str) -> bool:
        """Check text có phải keyword thoát mode."""
        text_lower = text.lower().strip()
        exit_keywords = ["xong", "hết", "đủ rồi", "đủ", "done", "stop", "không"]
        return any(text_lower == kw or text_lower.startswith(kw) for kw in exit_keywords)
```

---

## 1.4 — Wrap-up Handler

### File: `app/bot/handlers/wrap_up.py`

```python
"""
Wrap-up flow handlers.
"""

import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from app.services.wrap_up_service import WrapUpService
from app.services.transaction_service import TransactionService
from app.capture.voice.nlu_parser import parse_transaction_text  # Sẽ có ở tuần 5


async def send_daily_wrap_up(user):
    """Gọi từ scheduled job 20:30."""
    service = WrapUpService()
    message = await service.generate_summary(user)
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Đủ rồi", callback_data="wrap_up:complete"),
        InlineKeyboardButton("➕ Bổ sung", callback_data="wrap_up:add_more"),
    ]])
    
    from app.bot.bot_instance import bot
    await bot.send_message(
        chat_id=user.telegram_id,
        text=message,
        reply_markup=keyboard,
    )


async def handle_wrap_up_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    _, action = query.data.split(":")
    user_id = query.from_user.id
    
    service = WrapUpService()
    
    if action == "complete":
        completion_msg = random.choice(service._prompts["completion"])
        await query.edit_message_text(
            text=query.message.text + f"\n\n{completion_msg.format(name='bạn')}"
        )
    
    elif action == "add_more":
        # Vào wrap_up mode
        await service.enter_wrap_up_mode(user_id)
        followup = random.choice(service._prompts["followup_incomplete"])
        await query.message.reply_text(followup.format(name="bạn"))


async def handle_wrap_up_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Xử lý text message khi user đang trong wrap_up mode.
    Integration với message router: check is_in_wrap_up_mode trước khi route.
    """
    user_id = update.effective_user.id
    text = update.message.text
    service = WrapUpService()
    
    # Check exit keyword
    if service.is_exit_keyword(text):
        await service.exit_wrap_up_mode(user_id)
        completion_msg = random.choice(service._prompts["completion"])
        await update.message.reply_text(completion_msg.format(name="bạn"))
        return
    
    # Parse transaction từ text
    parsed = parse_transaction_text(text)
    
    if not parsed:
        await update.message.reply_text(
            "Mình chưa hiểu lắm 😅 Bạn gõ kiểu 'ăn phở 45k' hoặc '45000 cafe' giúp mình nhé"
        )
        return
    
    # Lưu với source = wrap_up
    tx_service = TransactionService()
    transaction = await tx_service.create_transaction(
        user_id=user_id,
        source="wrap_up",
        verified_by_user=True,  # User đã chủ động ghi trong wrap-up
        confidence=0.9,
        raw_input=text,
        **parsed,
    )
    
    # Confirm với keyboard
    from app.bot.formatters.templates import format_transaction_confirmation
    from app.bot.keyboards.transaction_keyboard import transaction_actions_keyboard
    
    text_response = format_transaction_confirmation(
        merchant=transaction.merchant,
        amount=transaction.amount,
        category_code=transaction.category_code,
    )
    
    # Thêm followup
    followup = random.choice(WrapUpService()._prompts["followup_more"])
    full_response = f"{text_response}\n\n{followup}"
    
    await update.message.reply_text(
        full_response,
        reply_markup=transaction_actions_keyboard(transaction.id),
    )
```

---

## 1.5 — Scheduled Job + Adaptive Timing

### File: `app/scheduled/daily_wrap_up.py`

```python
"""
Daily wrap-up scheduler.
Adaptive timing: gửi trước giờ active nhất của user 15 phút.
"""

import asyncio
from datetime import datetime, time
from app.services.user_service import UserService
from app.services.wrap_up_service import WrapUpService
from app.bot.handlers.wrap_up import send_daily_wrap_up


DEFAULT_WRAP_UP_TIME = time(20, 30)


async def run_daily_wrap_up():
    """Gọi mỗi 15 phút, check user nào cần gửi wrap-up bây giờ."""
    user_service = UserService()
    now = datetime.utcnow()
    
    # Lấy user active, đã opt-in wrap-up
    active_users = await user_service.get_active_users(days=14)
    
    for user in active_users:
        if not user.daily_wrap_up_enabled:  # Default True, user có thể tắt
            continue
        
        # Tính thời gian gửi cho user này
        send_time = await _compute_send_time(user)
        
        # Check nếu trong cửa sổ 15 phút tới send_time
        now_time = now.time()
        if _is_within_15_min(now_time, send_time):
            # Check nếu hôm nay đã gửi chưa
            if await _already_sent_today(user.id):
                continue
            
            try:
                await send_daily_wrap_up(user)
                await _mark_sent_today(user.id)
            except Exception as e:
                print(f"Wrap-up error user {user.id}: {e}")


async def _compute_send_time(user) -> time:
    """
    Tính giờ gửi wrap-up cho user dựa trên pattern.
    - Default: 20:30
    - Nếu user thường active late (>22h): gửi 21:45
    - Nếu user thường active early (<18h): gửi 19:30
    """
    # Query median hour của user events 30 ngày gần
    median_hour = await _get_user_active_hour(user.id)
    
    if median_hour is None:
        return DEFAULT_WRAP_UP_TIME
    
    if median_hour >= 22:
        return time(21, 45)
    elif median_hour <= 18:
        return time(19, 30)
    else:
        return DEFAULT_WRAP_UP_TIME


def _is_within_15_min(current: time, target: time) -> bool:
    """Check current có trong cửa sổ [target, target+15min] không."""
    # Simple minute-based check
    current_minutes = current.hour * 60 + current.minute
    target_minutes = target.hour * 60 + target.minute
    return 0 <= (current_minutes - target_minutes) < 15
```

---

## ✅ Checklist Cuối Tuần 1

- [ ] Migration add_transaction_source applied
- [ ] Wrap-up content YAML có ít nhất 4 variants
- [ ] `WrapUpService` hoàn chỉnh với state machine (Redis-backed)
- [ ] `send_daily_wrap_up` gửi được summary đúng format
- [ ] `handle_wrap_up_callback` xử lý "Đủ rồi" / "Bổ sung"
- [ ] `handle_wrap_up_text_input` parse và lưu transaction với source=wrap_up
- [ ] Exit keywords detect đúng (xong, hết, đủ rồi...)
- [ ] Timeout 15 phút tự động thoát mode
- [ ] Scheduled job chạy mỗi 15 phút
- [ ] Adaptive timing dựa trên user pattern
- [ ] User có thể tắt wrap-up trong settings
- [ ] Tự test E2E: gửi wrap-up cho chính bạn → "Bổ sung" → ghi 3 giao dịch → "xong"

---

# 📱 TUẦN 2: SMS Parsers — Foundation

> **Tuần này chỉ có PARSERS. Tuần 3 mới integrate với Telegram.** Tách ra vì parsers cần đầu tư thời gian test kỹ — nếu sai là sai lên DB thật.

## 2.1 — Thu Thập SMS Fixtures (Việc Quan Trọng Nhất Tuần Này)

**Đây là bottleneck — bạn làm được gì tuần này phụ thuộc vào có bao nhiêu mẫu SMS thật.**

### Cách thu thập:

- [ ] **Tự bạn:** Xem lại SMS của chính bạn, screenshot 20+ mẫu của bank bạn dùng
- [ ] **Bạn bè/gia đình:** Nhắn riêng, xin 5-10 mẫu mỗi bank khác nhau (redact account number)
- [ ] **Online sources:** Search "SMS ngân hàng Vietcombank example" trên Google Images, community forums
- [ ] **GitHub:** Search "VCB SMS parser" — có một số projects open-source có fixtures

### File: `app/capture/sms_parsers/fixtures/vcb_samples.txt`

```
# Format: mỗi block SMS cách nhau bằng ---
# Đầu mỗi block: # Expected: amount=X, direction=out/in, merchant=Y

# Expected: amount=150000, direction=out, merchant=GRAB*RIDE HANOI
TK VCB 1234: -150,000 VND luc 14:23 15/04.
Noi dung: GRAB*RIDE HANOI
SD: 5,250,000 VND

---

# Expected: amount=20000000, direction=in, merchant=CONG TY ABC
TK VCB 1234: +20,000,000 VND luc 09:00 01/04.
Noi dung: LUONG THANG 04 - CONG TY ABC
SD: 25,500,000 VND

---

# Expected: amount=85000, direction=out, merchant=HIGHLANDS COFFEE
TK VCB 1234: -85,000VND luc 09:15 16/04.
ND: HIGHLANDS COFFEE LANG HA
SD: 5,165,000VND

# Lưu ý: format này không có khoảng trắng trước VND — parser phải flexible

---

# OTP SMS (phải BỎ QUA, không parse)
VCB: Ma OTP cua ban la 123456. KHONG CHIA SE cho bat ky ai.

---

# Quảng cáo (phải BỎ QUA)
VCB: Uu dai vay the chap lai suat tu 6.5%. Lien he 1900545415.
```

**Nguyên tắc:** Mỗi bank cần **tối thiểu 20 samples** cover các case:
- Giao dịch out (chi)
- Giao dịch in (thu)
- Giao dịch lớn (lương)
- Giao dịch nhỏ (<50k)
- Có dấu
- Không dấu
- Chuyển khoản nội bộ
- Rút ATM
- Thanh toán QR
- **SMS KHÔNG PHẢI giao dịch** (OTP, quảng cáo) — parser phải bỏ qua

---

## 2.2 — Base Parser Interface

### File: `app/capture/sms_parsers/base.py`

```python
"""
Base interface cho tất cả SMS parsers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    OUT = "out"  # Chi
    IN = "in"    # Thu


@dataclass
class ParsedSMS:
    bank_code: str
    account_suffix: str  # Last 4 digits
    amount: float
    direction: Direction
    balance: Optional[float]  # Số dư sau giao dịch
    transaction_time: datetime
    description: str  # Raw description từ SMS
    merchant: Optional[str] = None  # Extract từ description
    confidence: float = 1.0
    raw_sms: str = ""


class SMSParser(ABC):
    bank_code: str = ""
    
    @abstractmethod
    def matches(self, sms_text: str) -> bool:
        """Check SMS có thuộc bank này không."""
        pass
    
    @abstractmethod
    def parse(self, sms_text: str) -> Optional[ParsedSMS]:
        """Parse SMS. Return None nếu không phải giao dịch (OTP, quảng cáo)."""
        pass
    
    def is_otp_or_promo(self, sms_text: str) -> bool:
        """Heuristics để loại SMS không phải giao dịch."""
        text_lower = sms_text.lower()
        otp_keywords = ["otp", "ma xac thuc", "ma kich hoat", "password"]
        promo_keywords = ["khuyen mai", "uu dai", "lai suat tu", "lien he", "dang ky"]
        
        if any(kw in text_lower for kw in otp_keywords):
            return True
        if any(kw in text_lower for kw in promo_keywords):
            return True
        
        # Giao dịch thực luôn có số tiền và VND
        if "vnd" not in text_lower:
            return True
        
        return False
```

---

## 2.3 — Vietcombank Parser (Most Common)

### File: `app/capture/sms_parsers/vcb.py`

```python
import re
from datetime import datetime
from app.capture.sms_parsers.base import SMSParser, ParsedSMS, Direction


class VCBParser(SMSParser):
    bank_code = "VCB"
    
    # Các pattern khác nhau VCB đã sử dụng qua các năm
    PATTERNS = [
        # Format mới (2023+): "TK VCB XXXX: -150,000 VND luc 14:23 15/04"
        re.compile(
            r"TK\s+VCB\s+(\d+).*?"
            r"([-+])([\d,\.]+)\s*VND\s*"
            r"luc\s+(\d{1,2}):(\d{2})\s+(\d{1,2})/(\d{1,2})(?:/(\d{4}))?.*?"
            r"(?:Noi dung|ND):\s*(.+?)(?:SD|$)",
            re.IGNORECASE | re.DOTALL,
        ),
        # Format cũ
        re.compile(
            r"VCB.*?(\d{4}).*?"
            r"([-+])([\d,\.]+).*?"
            r"(\d{1,2}):(\d{2}).*?"
            r"(\d{1,2})/(\d{1,2})",
            re.IGNORECASE | re.DOTALL,
        ),
    ]
    
    def matches(self, sms_text: str) -> bool:
        """VCB SMS thường có 'TK VCB' hoặc sender là 'Vietcombank'."""
        return (
            "tk vcb" in sms_text.lower() or
            "vietcombank" in sms_text.lower()
        )
    
    def parse(self, sms_text: str) -> ParsedSMS | None:
        if self.is_otp_or_promo(sms_text):
            return None
        
        for pattern in self.PATTERNS:
            match = pattern.search(sms_text)
            if match:
                return self._build_from_match(match, sms_text)
        
        return None
    
    def _build_from_match(self, match, raw_sms: str) -> ParsedSMS:
        groups = match.groups()
        
        account_suffix = groups[0][-4:]
        direction = Direction.OUT if groups[1] == "-" else Direction.IN
        amount = float(groups[2].replace(",", "").replace(".", ""))
        
        hour = int(groups[3])
        minute = int(groups[4])
        day = int(groups[5])
        month = int(groups[6])
        year = int(groups[7]) if len(groups) > 7 and groups[7] else datetime.now().year
        
        transaction_time = datetime(year, month, day, hour, minute)
        
        description = groups[8].strip() if len(groups) > 8 and groups[8] else ""
        # Strip balance info nếu còn
        description = re.sub(r"SD:.*$", "", description, flags=re.IGNORECASE).strip()
        
        # Extract balance
        balance_match = re.search(r"SD:\s*([\d,\.]+)", raw_sms, re.IGNORECASE)
        balance = None
        if balance_match:
            balance = float(balance_match.group(1).replace(",", "").replace(".", ""))
        
        # Extract merchant từ description
        merchant = self._extract_merchant(description)
        
        return ParsedSMS(
            bank_code=self.bank_code,
            account_suffix=account_suffix,
            amount=amount,
            direction=direction,
            balance=balance,
            transaction_time=transaction_time,
            description=description,
            merchant=merchant,
            confidence=0.95,
            raw_sms=raw_sms,
        )
    
    def _extract_merchant(self, description: str) -> str:
        """
        Extract merchant từ description.
        Examples:
          "GRAB*RIDE HANOI" → "Grab"
          "HIGHLANDS COFFEE LANG HA" → "Highlands Coffee"
          "CK den CTK NGUYEN VAN A" → "Nguyen Van A"
        """
        description = description.strip()
        
        # Pattern: "MERCHANT*XXX" → MERCHANT
        if "*" in description:
            return description.split("*")[0].title()
        
        # Pattern: chuyển khoản "CK den CTK X"
        ck_match = re.search(r"CK\s+den\s+CTK\s+(.+?)(?:$|,|\s{2,})", description, re.IGNORECASE)
        if ck_match:
            return ck_match.group(1).strip().title()
        
        # Default: title case của description
        words = description.split()
        if len(words) > 4:
            return " ".join(words[:4]).title()
        return description.title()
```

### Test: `tests/test_sms_parsers/test_vcb.py`

```python
import pytest
from pathlib import Path
from app.capture.sms_parsers.vcb import VCBParser


def load_fixtures():
    """Load và parse fixture file thành list (sms, expected)."""
    path = Path("app/capture/sms_parsers/fixtures/vcb_samples.txt")
    content = path.read_text(encoding="utf-8")
    
    samples = []
    blocks = content.split("---")
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        
        # Parse expected comment
        expected = {}
        lines = block.split("\n")
        sms_lines = []
        for line in lines:
            if line.startswith("# Expected:"):
                parts = line.replace("# Expected:", "").strip().split(", ")
                for part in parts:
                    k, v = part.split("=")
                    expected[k.strip()] = v.strip()
            elif not line.startswith("#"):
                sms_lines.append(line)
        
        sms = "\n".join(sms_lines).strip()
        if sms:
            samples.append((sms, expected))
    
    return samples


@pytest.mark.parametrize("sms,expected", load_fixtures())
def test_vcb_parse(sms, expected):
    parser = VCBParser()
    
    if not expected:  # OTP/promo — phải return None
        result = parser.parse(sms)
        assert result is None, f"Should not parse non-transaction: {sms[:50]}"
        return
    
    result = parser.parse(sms)
    assert result is not None, f"Failed to parse: {sms}"
    
    if "amount" in expected:
        assert result.amount == float(expected["amount"])
    if "direction" in expected:
        assert result.direction.value == expected["direction"]
    if "merchant" in expected:
        assert expected["merchant"].lower() in result.merchant.lower()


def test_vcb_does_not_match_techcom():
    """Parser không được claim ownership SMS của bank khác."""
    parser = VCBParser()
    techcom_sms = "TCB: Tai khoan 1234 -50,000 VND..."
    assert not parser.matches(techcom_sms)
```

---

## 2.4 — Các Parser Khác + Registry

Làm tương tự cho 4 banks còn lại. Lưu ý format differences:

**Techcombank:**
```
TCB: TK 1234 biến động -50,000 VND tại GRAB. SD: 3,200,000 VND
```

**MB Bank:**
```
TK MB 1234: -50000VND 15/04/25 14:23. ND: THANH TOAN QR GRAB. SD: 3200000
```

**ACB:**
```
ACB: -50,000 VND 15-04. GD: GRAB*HANOI. SDKD: 3,200,000
```

**VPBank:**
```
VPB: PS: -50,000 VND tai GRAB. TGD 14:23 15/04. SDKD: 3,200,000
```

### File: `app/capture/sms_parsers/registry.py`

```python
"""
Auto-detect bank và route tới parser phù hợp.
"""

from app.capture.sms_parsers.vcb import VCBParser
from app.capture.sms_parsers.techcombank import TechcomParser
from app.capture.sms_parsers.mb import MBParser
from app.capture.sms_parsers.acb import ACBParser
from app.capture.sms_parsers.vpbank import VPBParser


PARSERS = [
    VCBParser(),
    TechcomParser(),
    MBParser(),
    ACBParser(),
    VPBParser(),
]


def parse_sms(sms_text: str):
    """
    Try all parsers, return first match.
    """
    for parser in PARSERS:
        if parser.matches(sms_text):
            return parser.parse(sms_text)
    
    return None


def get_supported_banks() -> list[str]:
    return [p.bank_code for p in PARSERS]
```

---

## ✅ Checklist Cuối Tuần 2

- [ ] Fixtures: mỗi bank có >20 samples, bao gồm OTP/promo
- [ ] `base.py` với SMSParser interface
- [ ] 5 parsers: VCB, Techcom, MB, ACB, VPBank
- [ ] Mỗi parser có test file riêng, tests **pass 100%** trên fixtures
- [ ] Registry auto-detect bank từ SMS
- [ ] Parser trả về None cho OTP/quảng cáo (KHÔNG raise exception)
- [ ] Merchant extraction smart cho các pattern phổ biến (GRAB*, CK den CTK...)
- [ ] Test với 5 bạn bè forward cho ít nhất 10 SMS thật — parse success rate >90%

**Quality gate:** Không sang tuần 3 nếu parser < 90% accuracy trên fixtures.

---

# 🔌 TUẦN 3: SMS Integration + Forwarder Guide

## 3.1 — Raw SMS Model (Audit + Debug)

### Migration + Model

```python
# Lưu MỌI SMS nhận được, kể cả parse fail
# Lý do: debug, improve parsers, legal audit

class RawSMS(Base):
    __tablename__ = "raw_sms"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    raw_text = Column(Text, nullable=False)
    received_at = Column(DateTime, default=datetime.utcnow)
    
    # Parse results
    parsed = Column(Boolean, default=False)
    parser_used = Column(String(20), nullable=True)  # VCB, TCB, ...
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    parse_error = Column(Text, nullable=True)
    
    # Privacy: encrypted if contains sensitive info
    # (Tiến dần: plaintext tuần này, encrypted khi scale)
```

---

## 3.2 — SMS Forward Handler

### File: `app/bot/handlers/sms_forward.py`

```python
"""
Xử lý SMS forwarded từ user tới bot.
"""

import re
from telegram import Update
from telegram.ext import ContextTypes

from app.capture.sms_parsers.registry import parse_sms
from app.services.transaction_service import TransactionService
from app.services.capture_service import CaptureService


def looks_like_bank_sms(text: str) -> bool:
    """
    Heuristic: check xem text có giống SMS ngân hàng không.
    Dùng để distinguish với text bình thường user gõ.
    """
    text_lower = text.lower()
    indicators = [
        "vnd",
        "tk ",
        "tài khoản",
        "sd:", "sdkd:", "so du",
        "luc", "tgd",
    ]
    # Need at least 2 indicators + amount pattern
    count = sum(1 for ind in indicators if ind in text_lower)
    has_amount = bool(re.search(r"[\d,\.]+\s*vnd", text_lower))
    
    return count >= 2 and has_amount


async def handle_potential_sms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Called BEFORE regular text handler.
    Nếu text giống SMS bank → route tới đây.
    """
    text = update.message.text
    user_id = update.effective_user.id
    
    if not looks_like_bank_sms(text):
        return False  # Not SMS, pass to regular handler
    
    capture_service = CaptureService()
    result = await capture_service.process_sms(user_id, text)
    
    if result.success:
        # Transaction đã tạo, confirm với inline keyboard
        from app.bot.formatters.templates import format_transaction_confirmation
        from app.bot.keyboards.transaction_keyboard import transaction_actions_keyboard
        
        msg = format_transaction_confirmation(
            merchant=result.transaction.merchant,
            amount=result.transaction.amount,
            category_code=result.transaction.category_code,
        )
        msg = f"📱 Từ SMS {result.bank_code}:\n\n{msg}"
        
        await update.message.reply_text(
            msg,
            reply_markup=transaction_actions_keyboard(result.transaction.id),
        )
    else:
        # Parse fail — ask user
        await _handle_parse_failure(update, text, result.reason)
    
    return True


async def _handle_parse_failure(update, raw_sms: str, reason: str):
    """Không parse được → hỏi user."""
    await update.message.reply_text(
        "Mình nhận được SMS này nhưng chưa đọc ra được 😅\n\n"
        "Bạn nhập giúp mình nhanh nhé:\n"
        "• Số tiền?\n"
        "• Chi vào đâu?\n\n"
        "Hoặc tap [Bỏ qua] nếu không phải giao dịch."
    )
    # Lưu raw SMS để debug later
```

### File: `app/services/capture_service.py`

Unified API cho mọi capture method:

```python
from dataclasses import dataclass
from typing import Optional
from app.capture.sms_parsers.registry import parse_sms
from app.categorizer.rule_engine import categorize
from app.models.raw_sms import RawSMS


@dataclass
class CaptureResult:
    success: bool
    transaction: Optional["Transaction"] = None
    bank_code: Optional[str] = None
    reason: str = ""


class CaptureService:
    async def process_sms(self, user_id: int, sms_text: str) -> CaptureResult:
        """Main entry point cho SMS capture."""
        # 1. Save raw SMS (audit log)
        raw = await self._save_raw(user_id, sms_text)
        
        # 2. Parse
        parsed = parse_sms(sms_text)
        
        if parsed is None:
            raw.parse_error = "No parser matched or non-transaction SMS"
            await self._update_raw(raw)
            return CaptureResult(
                success=False,
                reason="Could not parse SMS",
            )
        
        # 3. Check duplicate
        if await self._is_duplicate(user_id, parsed):
            raw.parse_error = "Duplicate"
            await self._update_raw(raw)
            return CaptureResult(success=False, reason="Duplicate transaction")
        
        # 4. Skip nếu chuyển khoản nội bộ (same user's account)
        if await self._is_internal_transfer(user_id, parsed):
            return CaptureResult(success=False, reason="Internal transfer")
        
        # 5. Categorize
        category = await categorize(
            merchant=parsed.merchant,
            description=parsed.description,
            user_id=user_id,
        )
        
        # 6. Save transaction
        from app.services.transaction_service import TransactionService
        tx_service = TransactionService()
        transaction = await tx_service.create_transaction(
            user_id=user_id,
            amount=parsed.amount,
            merchant=parsed.merchant,
            category_code=category.code,
            transaction_time=parsed.transaction_time,
            source="sms",
            confidence=parsed.confidence,
            raw_input=sms_text,
            description=parsed.description,
        )
        
        # 7. Link raw SMS → transaction
        raw.parsed = True
        raw.parser_used = parsed.bank_code
        raw.transaction_id = transaction.id
        await self._update_raw(raw)
        
        return CaptureResult(
            success=True,
            transaction=transaction,
            bank_code=parsed.bank_code,
        )
    
    async def _is_duplicate(self, user_id: int, parsed) -> bool:
        """
        Check xem giao dịch đã có chưa (user forward SMS 2 lần).
        Match theo: amount + time (±5 min) + bank.
        """
        # Implementation...
        pass
    
    async def _is_internal_transfer(self, user_id: int, parsed) -> bool:
        """
        Nếu user có 2 tài khoản trong cùng bank/bank khác, và giao dịch này
        là chuyển khoản giữa chúng → skip (không tính chi/thu).
        """
        # Cần table user_accounts để biết user có những account nào
        pass
```

---

## 3.3 — Forwarder Setup Guide

### File: `content/forwarder_guides/vcb_android.md`

```markdown
# Cách Tự Động Forward SMS VCB Vào Bot

## Bạn Cần:
- Điện thoại Android
- 5 phút

## Bước 1: Cài App "SMS Forwarder"

1. Vào Google Play Store
2. Search "SMS Forwarder Pro" (tác giả: FNamic) — **MIỄN PHÍ**
3. Cài và mở app

## Bước 2: Cấp Permission

- Cho phép đọc SMS khi app hỏi
- Cho phép chạy nền (Battery Optimization → Don't Optimize)

## Bước 3: Tạo Forwarding Rule

1. Tap "+ New Rule"
2. **From:** Chọn "Vietcombank" hoặc số +84... của VCB
3. **To:** Telegram
   - Bot Token: (app sẽ hỏi — copy từ tin nhắn này)
   - Chat ID: (app sẽ hỏi — copy từ tin nhắn này)
4. Tap "Save"

## Bước 4: Test

1. Đợi SMS VCB tiếp theo (hoặc tự chuyển 10k rồi rút)
2. Kiểm tra bot đã nhận chưa

## Khi Có Vấn Đề

- SMS không forward: kiểm tra app có quyền background
- Bot không nhận: check lại Chat ID
- Parse không đúng: forward SMS kèm message "SMS parse sai" — mình sẽ fix
```

### Thêm setup flow trong Mini App

```html
<!-- /miniapp/setup-sms -->
<div class="setup-wizard">
  <h1>Tự động ghi giao dịch từ SMS</h1>
  <p>Đây là cách nhanh nhất để không bao giờ quên giao dịch nào.</p>
  
  <div class="platform-picker">
    <button onclick="selectAndroid()">📱 Android</button>
    <button onclick="selectiOS()">📱 iPhone</button>
  </div>
  
  <!-- Android flow -->
  <div id="android-flow" style="display:none">
    <ol>
      <li>Chọn ngân hàng của bạn</li>
      <li>Cài app SMS Forwarder (link Play Store)</li>
      <li>Copy tokens này vào app:
        <div class="token-box">
          <div>Bot Token: <code id="bot-token">...</code> <button>Copy</button></div>
          <div>Chat ID: <code id="chat-id">...</code> <button>Copy</button></div>
        </div>
      </li>
      <li>Done! Gửi 1 SMS test để verify</li>
    </ol>
  </div>
  
  <!-- iOS flow: sẽ làm ở section sau -->
  <div id="ios-flow" style="display:none">
    <p>iPhone không forward được SMS trực tiếp, nhưng bạn có các options khác:</p>
    <ul>
      <li>🍎 Apple Shortcuts (nâng cao)</li>
      <li>📸 Screenshot OCR (đơn giản nhất)</li>
      <li>📧 Email forwarding từ bank</li>
    </ul>
  </div>
</div>
```

---

## 3.4 — iPhone Strategy

Đây là section **đặc biệt quan trọng** mà strategy gốc chưa cover kỹ.

### Option A: Apple Shortcuts (Power users)

Viết 1 Shortcut that:
1. Trigger: Nhận SMS từ bank
2. Action: Gửi HTTP POST tới webhook của bot
3. Share link Shortcut: `https://www.icloud.com/shortcuts/xxx`

**Documentation:** Viết guide chi tiết với screenshots.

### Option B: Email Forwarding

Nhiều bank VN (VCB, Techcom) có option **gửi email** kèm theo SMS cho mỗi giao dịch. 

**Flow:**
1. User vào Internet Banking → bật "Email notification"
2. User tạo filter trong Gmail: forward emails từ `no-reply@vietcombank.com.vn` → `sms@yourbot.com`
3. Your backend nhận email qua SendGrid/Mailgun inbound webhook
4. Parse email body (format khác SMS nhưng tương tự)

**Pros:** Cross-platform, robust
**Cons:** Cần user vào IB setup, delay 1-2 phút

### Option C: Emphasize OCR + Wrap-up

Cho iPhone users **không quá tech-savvy**, explicit hóa rằng:
- "Bạn chụp màn hình thông báo app bank → gửi bot"
- "Wrap-up cuối ngày sẽ hỏi lại nếu quên gì"
- Tỉ lệ auto sẽ ~60% (vs 90% Android) nhưng vẫn tốt hơn ghi tay 100%

Viết honest message khi user chọn iPhone trong onboarding:
```
iPhone không forward SMS tự động được 😔
Nhưng mình có 3 cách khác:

📸 Chụp màn hình (đơn giản, hiệu quả)
📧 Email forward (setup 5 phút, chạy mãi)
🔧 Apple Shortcuts (nâng cao, 15 phút)

Chọn cái bạn muốn thử?
```

---

## ✅ Checklist Cuối Tuần 3

- [ ] `RawSMS` model + migration
- [ ] Handler `handle_potential_sms` detect và route SMS
- [ ] `CaptureService.process_sms` lưu transaction + audit log
- [ ] Duplicate detection hoạt động
- [ ] Internal transfer detection (nếu user có >1 account)
- [ ] Forwarder guide viết đầy đủ cho 5 bank + iOS alternatives
- [ ] Mini App setup wizard cho SMS forward
- [ ] Bot gửi unique Bot Token + Chat ID cho mỗi user
- [ ] iPhone: ít nhất 1 alternative path (email forward hoặc OCR-first)
- [ ] Test E2E: friend Android forward SMS → transaction lên đẹp

---

# 📸 TUẦN 4: Screenshot OCR

## 4.1 — Claude Vision Wrapper

### File: `app/capture/ocr/vision_client.py`

```python
"""
Claude Vision wrapper cho OCR screenshots.
"""

import base64
import hashlib
import json
from pathlib import Path
from anthropic import AsyncAnthropic

from app.config import settings
from app.capture.ocr.cache import OCRCache


client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


OCR_PROMPT = """Đây là screenshot giao dịch từ app ngân hàng hoặc ví điện tử Việt Nam.

Trích xuất các thông tin sau dưới dạng JSON:
{
  "amount": <number, đơn vị VND, không dấu phẩy>,
  "direction": "out" hoặc "in",
  "merchant": "<người nhận/shop/đơn vị, chuẩn hóa Title Case>",
  "transaction_time": "<YYYY-MM-DD HH:MM hoặc null nếu không thấy>",
  "payment_method": "<momo/zalopay/vnpay/bank_app/other>",
  "note": "<nội dung/ghi chú nếu có>",
  "confidence": <0.0-1.0, đánh giá độ chắc chắn của bạn>
}

Nếu ảnh KHÔNG PHẢI giao dịch tài chính, return:
{"confidence": 0.0, "reason": "not_a_transaction"}

QUY TẮC:
- Không đoán khi không thấy rõ. Return null cho field không chắc.
- Amount phải là số nguyên (không lẻ đồng)
- Merchant: loại bỏ phần "GRAB*" prefix, giữ tên chính (VD: "GRAB*RIDE" → "Grab")
- Nếu screenshot mờ/cắt, confidence < 0.6

Chỉ trả về JSON, không giải thích thêm."""


async def extract_transaction_from_image(image_bytes: bytes) -> dict:
    """
    Gọi Claude Vision extract giao dịch từ ảnh.
    """
    # Check cache first
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    cached = await OCRCache.get(image_hash)
    if cached:
        return cached
    
    # Resize nếu quá lớn (giảm cost)
    image_bytes = _resize_if_needed(image_bytes, max_dimension=1568)
    
    # Encode base64
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    
    # Call Claude Vision
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",  # Haiku is cheaper & faster for OCR
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_b64,
                    },
                },
                {
                    "type": "text",
                    "text": OCR_PROMPT,
                },
            ],
        }],
    )
    
    # Parse response
    text = response.content[0].text.strip()
    
    # Strip markdown code fences if present
    text = text.replace("```json", "").replace("```", "").strip()
    
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        result = {"confidence": 0.0, "reason": "parse_error", "raw": text}
    
    # Cache
    await OCRCache.set(image_hash, result)
    
    return result


def _resize_if_needed(image_bytes: bytes, max_dimension: int) -> bytes:
    """Resize image để giảm token cost."""
    from PIL import Image
    from io import BytesIO
    
    img = Image.open(BytesIO(image_bytes))
    
    if max(img.size) <= max_dimension:
        return image_bytes
    
    ratio = max_dimension / max(img.size)
    new_size = tuple(int(dim * ratio) for dim in img.size)
    img = img.resize(new_size, Image.LANCZOS)
    
    output = BytesIO()
    img.convert("RGB").save(output, format="JPEG", quality=85)
    return output.getvalue()
```

### File: `app/capture/ocr/cache.py`

```python
"""
Cache OCR results by image hash.
Lý do: user có thể gửi lại cùng 1 ảnh; cost OCR không rẻ.
"""

import json
from app.cache import redis_client


class OCRCache:
    PREFIX = "ocr:"
    TTL = 30 * 24 * 3600  # 30 days
    
    @classmethod
    async def get(cls, image_hash: str) -> dict | None:
        raw = await redis_client.get(f"{cls.PREFIX}{image_hash}")
        if raw:
            return json.loads(raw)
        return None
    
    @classmethod
    async def set(cls, image_hash: str, data: dict):
        await redis_client.set(
            f"{cls.PREFIX}{image_hash}",
            json.dumps(data),
            ex=cls.TTL,
        )
```

---

## 4.2 — Screenshot Handler

### File: `app/bot/handlers/screenshot.py`

```python
"""
Handle photo messages from Telegram.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from app.capture.ocr.vision_client import extract_transaction_from_image
from app.services.capture_service import CaptureService


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Get largest photo
    photo = update.message.photo[-1]
    photo_file = await photo.get_file()
    
    # Show "đang xử lý" feedback
    processing_msg = await update.message.reply_text("📸 Đang đọc ảnh...")
    
    try:
        # Download
        image_bytes = await photo_file.download_as_bytearray()
        
        # OCR
        result = await extract_transaction_from_image(bytes(image_bytes))
        
        # Handle result
        if result.get("confidence", 0) < 0.3:
            await processing_msg.edit_text(
                "Mình không chắc đây có phải giao dịch không 🤔\n\n"
                "Bạn gõ tay giúp mình nhé? Ví dụ: '150k grab'"
            )
            return
        
        if result.get("confidence", 0) < 0.7:
            # Low confidence — ask user to verify
            await _confirm_low_confidence(update, processing_msg, result)
            return
        
        # High confidence — save directly với keyboard
        await _save_from_ocr(update, processing_msg, result, user_id)
        
    except Exception as e:
        await processing_msg.edit_text(
            "Có lỗi đọc ảnh 😔 Bạn thử gõ tay nhé?"
        )
        # Log error
        print(f"OCR error for user {user_id}: {e}")


async def _save_from_ocr(update, processing_msg, ocr_result, user_id):
    """Save transaction from high-confidence OCR."""
    capture_service = CaptureService()
    result = await capture_service.process_ocr_result(user_id, ocr_result)
    
    if result.success:
        from app.bot.formatters.templates import format_transaction_confirmation
        from app.bot.keyboards.transaction_keyboard import transaction_actions_keyboard
        
        text = format_transaction_confirmation(
            merchant=result.transaction.merchant,
            amount=result.transaction.amount,
            category_code=result.transaction.category_code,
        )
        text = f"📸 Từ ảnh ({ocr_result.get('payment_method', '').upper()}):\n\n{text}"
        
        await processing_msg.edit_text(
            text=text,
            reply_markup=transaction_actions_keyboard(result.transaction.id),
        )


async def _confirm_low_confidence(update, processing_msg, ocr_result):
    """
    Confidence 0.3-0.7: show result, ask user to confirm/edit.
    """
    amount = ocr_result.get("amount", "?")
    merchant = ocr_result.get("merchant", "?")
    
    text = (
        f"📸 Mình đọc được:\n\n"
        f"💰 Số tiền: {amount:,}đ\n"
        f"🏪 Chỗ: {merchant}\n\n"
        f"Có đúng không?"
    )
    
    # Store OCR result in user state để save khi user confirm
    # (Dùng Redis hoặc in-memory state)
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Đúng", callback_data="ocr:confirm"),
        InlineKeyboardButton("✏️ Sửa", callback_data="ocr:edit"),
        InlineKeyboardButton("❌ Bỏ qua", callback_data="ocr:skip"),
    ]])
    
    await processing_msg.edit_text(text, reply_markup=keyboard)
```

---

## 4.3 — Batch Processing

### Khi user gửi nhiều ảnh cùng lúc

Telegram gửi từng photo riêng biệt nhưng rất gần nhau (<1s). Pattern: buffer photos trong 3s, xử lý batch.

```python
# app/bot/handlers/screenshot.py

_photo_buffer = {}  # {user_id: [photo_files, timer_task]}


async def handle_photo_batched(update, context):
    user_id = update.effective_user.id
    photo = update.message.photo[-1]
    
    if user_id not in _photo_buffer:
        _photo_buffer[user_id] = {"photos": [], "timer": None}
    
    _photo_buffer[user_id]["photos"].append(photo)
    
    # Cancel previous timer
    if _photo_buffer[user_id]["timer"]:
        _photo_buffer[user_id]["timer"].cancel()
    
    # Start new timer 3s
    import asyncio
    _photo_buffer[user_id]["timer"] = asyncio.create_task(
        _process_batch_after_delay(user_id, update, delay=3)
    )


async def _process_batch_after_delay(user_id, update, delay):
    await asyncio.sleep(delay)
    
    batch = _photo_buffer.pop(user_id, None)
    if not batch:
        return
    
    photos = batch["photos"]
    
    # Send progress
    progress_msg = await update.message.reply_text(
        f"📸 Đang xử lý {len(photos)} ảnh..."
    )
    
    # Process parallel
    results = await asyncio.gather(*[
        _process_single_photo(photo, user_id) for photo in photos
    ])
    
    # Summary
    success_count = sum(1 for r in results if r.success)
    text = (
        f"✅ Xong!\n"
        f"• {success_count}/{len(photos)} ảnh đã ghi\n"
        f"• {len(photos) - success_count} ảnh cần xem lại"
    )
    await progress_msg.edit_text(text)
```

---

## ✅ Checklist Cuối Tuần 4

- [ ] Claude Vision integration hoạt động
- [ ] OCR cache (Redis) reduce cost
- [ ] Image resize trước khi gửi API
- [ ] Prompt tested với ảnh từ MoMo, ZaloPay, VCB app, Techcom app
- [ ] Confidence thresholds: >0.7 auto save, 0.3-0.7 confirm, <0.3 reject
- [ ] Batch processing (multiple photos within 3s)
- [ ] Error handling (network error, API error, parse error)
- [ ] Test với 20+ screenshots thật từ nhiều apps

---

# 🎤 TUẦN 5: Voice Input + Smart Categorizer

> Tuần này có 2 tracks, có thể làm song song: Voice và Categorizer. Categorizer quan trọng hơn — vì nó enable auto-categorize cho SMS (tuần 2-3) và OCR (tuần 4).

## 5.1 — Smart Categorizer (Prioritize!)

### File: `app/categorizer/rule_engine.py`

```python
"""
Rule-based categorizer.
Ưu tiên 1: Per-user learned rules
Ưu tiên 2: Global default rules
Ưu tiên 3: LLM fallback
"""

import yaml
from pathlib import Path
from dataclasses import dataclass
from app.models.merchant_rule import MerchantRule
from app.database import get_session


@dataclass
class CategorizeResult:
    code: str
    confidence: float
    source: str  # "user_rule", "default_rule", "llm", "fallback"


# Load default rules
DEFAULT_RULES = yaml.safe_load(Path("app/categorizer/rules.yaml").read_text(encoding="utf-8"))


async def categorize(
    merchant: str,
    description: str = "",
    user_id: int = None,
) -> CategorizeResult:
    """
    Main entry: categorize giao dịch.
    """
    text_to_match = f"{merchant} {description}".lower()
    
    # 1. User-specific learned rules
    if user_id:
        user_result = await _match_user_rules(user_id, text_to_match)
        if user_result:
            return user_result
    
    # 2. Default global rules
    default_result = _match_default_rules(text_to_match)
    if default_result:
        return default_result
    
    # 3. LLM fallback
    from app.categorizer.llm_fallback import categorize_via_llm
    llm_result = await categorize_via_llm(merchant, description)
    if llm_result.confidence > 0.5:
        return llm_result
    
    # 4. Fallback
    return CategorizeResult(code="other", confidence=0.0, source="fallback")


async def _match_user_rules(user_id: int, text: str) -> CategorizeResult | None:
    async with get_session() as session:
        rules = await session.query(MerchantRule).filter_by(user_id=user_id).all()
        for rule in rules:
            if rule.pattern.lower() in text:
                return CategorizeResult(
                    code=rule.category_code,
                    confidence=0.95,
                    source="user_rule",
                )
    return None


def _match_default_rules(text: str) -> CategorizeResult | None:
    for category_code, patterns in DEFAULT_RULES.items():
        for pattern in patterns:
            if pattern.lower() in text:
                return CategorizeResult(
                    code=category_code,
                    confidence=0.85,
                    source="default_rule",
                )
    return None
```

### File: `app/categorizer/rules.yaml`

```yaml
# Default categorization rules - merchant keyword → category
# Start với các merchant phổ biến VN, expand over time

food:
  - grab food
  - grabfood
  - shopeefood
  - beamin
  - baemin
  - now
  - loship
  - phở
  - pho
  - bún
  - bun
  - cơm
  - com
  - lotteria
  - kfc
  - mcdonald
  - burger king
  - pizza
  - highlands coffee
  - starbucks
  - the coffee house
  - phuc long
  - cheese coffee
  - circle k
  - vinmart
  - coopmart
  - bach hoa xanh
  - lottemart

transport:
  - grab car
  - grab bike
  - grabride
  - grab*ride
  - be
  - gojek
  - xăng
  - xang
  - petrolimex
  - pvoil
  - parking
  - bai do
  - đậu xe
  - taxi
  - mai linh
  - vinasun
  - vnr
  - vietnam railways

housing:
  - điện lực
  - dien luc
  - evn
  - nước
  - sawaco
  - tien nha
  - tiền nhà
  - rent
  - apartment

utility:
  - internet
  - fpt
  - viettel
  - vnpt
  - mobifone
  - vinaphone
  - zalopay bill
  - momo bill

shopping:
  - shopee
  - lazada
  - tiki
  - sendo
  - uniqlo
  - zara
  - h&m
  - the gioi di dong
  - dien may xanh
  - nguyen kim

health:
  - nhà thuốc
  - nha thuoc
  - pharmacity
  - long chau
  - guardian
  - bệnh viện
  - benh vien
  - hospital
  - clinic
  - phong kham

entertainment:
  - cgv
  - lotte cinema
  - bhd
  - galaxy cinema
  - netflix
  - spotify
  - youtube premium
  - steam
  - playstation

education:
  - hoc phi
  - học phí
  - tuition
  - school
  - truong
  - trường
  - coursera
  - udemy

transfer:
  - ck den
  - chuyen khoan
  - chuyển khoản
  - ctk
  - tk chinh chu
```

### File: `app/categorizer/llm_fallback.py`

```python
"""
LLM fallback when rules don't match.
Use DeepSeek (primary) per user's stack.
"""

import json
from app.config import settings


async def categorize_via_llm(merchant: str, description: str = "") -> CategorizeResult:
    """
    Dùng DeepSeek để categorize merchant không match rule.
    """
    from openai import AsyncOpenAI  # DeepSeek compatible with OpenAI SDK
    
    client = AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com/v1",
    )
    
    prompt = f"""Phân loại giao dịch tài chính sau vào 1 trong các categories:
- food: Ăn uống, nhà hàng, cafe, đồ ăn
- transport: Di chuyển, xăng, taxi, Grab
- housing: Nhà cửa, điện nước, tiền thuê
- shopping: Mua sắm, quần áo, đồ dùng
- health: Sức khỏe, thuốc, bệnh viện
- education: Giáo dục, học phí, sách
- entertainment: Giải trí, phim, game
- utility: Tiện ích, internet, điện thoại
- transfer: Chuyển khoản
- other: Khác

Merchant: {merchant}
Description: {description}

Trả về JSON: {{"category": "...", "confidence": 0.0-1.0}}"""
    
    response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        max_tokens=100,
    )
    
    try:
        result = json.loads(response.choices[0].message.content)
        return CategorizeResult(
            code=result["category"],
            confidence=result.get("confidence", 0.7),
            source="llm",
        )
    except (json.JSONDecodeError, KeyError):
        return CategorizeResult(code="other", confidence=0.3, source="llm")
```

---

## 5.2 — Learning From Corrections

### File: `app/categorizer/learning.py`

**Đây là secret sauce.** Khi user sửa category, ta learn.

```python
"""
Learning service: when user changes category, save as rule.
"""

from app.models.merchant_rule import MerchantRule
from app.database import get_session


class LearningService:
    async def record_correction(
        self,
        user_id: int,
        merchant: str,
        old_category: str,
        new_category: str,
        raw_input: str = None,
    ):
        """
        Gọi khi user tap "Đổi danh mục" trong Phase 1's inline keyboard.
        """
        # Extract merchant key để match future transactions
        merchant_key = self._extract_key(merchant, raw_input)
        
        async with get_session() as session:
            # Check existing rule cho merchant này
            existing = await session.query(MerchantRule).filter_by(
                user_id=user_id,
                pattern=merchant_key,
            ).first()
            
            if existing:
                # Update category
                existing.category_code = new_category
                existing.confidence += 0.05  # Reinforcement
                existing.updated_at = datetime.utcnow()
            else:
                # New rule
                new_rule = MerchantRule(
                    user_id=user_id,
                    pattern=merchant_key,
                    category_code=new_category,
                    confidence=0.85,
                )
                session.add(new_rule)
            
            await session.commit()
        
        # Track
        from app.analytics import track, Event
        await track(Event(
            user_id=user_id,
            event_type="category_corrected",
            properties={
                "merchant": merchant,
                "old": old_category,
                "new": new_category,
            },
            timestamp=datetime.utcnow(),
        ))
    
    def _extract_key(self, merchant: str, raw_input: str = None) -> str:
        """
        Extract stable key để match future.
        Examples:
          "Highlands Coffee Láng Hạ" → "highlands coffee"
          "GRAB*RIDE HANOI 15/04" → "grab ride"
        """
        # Lowercase
        key = merchant.lower()
        
        # Remove location suffixes
        import re
        key = re.sub(r"\s+(hn|hanoi|hcm|ho chi minh|da nang|hai phong|.+city)$", "", key)
        
        # Remove date
        key = re.sub(r"\d{1,2}/\d{1,2}(/\d{2,4})?", "", key)
        
        # Remove extra whitespace
        key = " ".join(key.split())
        
        # Take first 3 meaningful words
        words = key.split()[:3]
        return " ".join(words)
```

### Integration với Phase 1's callback handler

```python
# Update app/bot/handlers/callbacks.py

async def handle_change_category(update, context, args, user_id):
    if len(args) == 2:  # User đã chọn category mới
        transaction_id = int(args[0])
        new_category = args[1]
        
        # Existing: update transaction
        service = TransactionService()
        transaction = await service.update_category(...)
        
        # NEW: record as learning signal
        from app.categorizer.learning import LearningService
        learning = LearningService()
        await learning.record_correction(
            user_id=user_id,
            merchant=transaction.merchant,
            old_category=transaction.previous_category,
            new_category=new_category,
            raw_input=transaction.raw_input,
        )
```

---

## 5.3 — Voice Input

### File: `app/capture/voice/whisper_client.py`

```python
"""
Whisper client via OpenAI API.
Alternatives: self-host when scale.
"""

from openai import AsyncOpenAI
from app.config import settings


client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def transcribe_vietnamese(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """
    Transcribe Vietnamese voice message.
    Telegram sends OGG Opus format.
    """
    from io import BytesIO
    
    audio_file = BytesIO(audio_bytes)
    audio_file.name = filename
    
    response = await client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="vi",  # Hint Vietnamese
        response_format="text",
    )
    
    return response.strip()
```

### File: `app/capture/voice/nlu_parser.py`

```python
"""
Parse Vietnamese transaction phrases.
Used for: voice transcripts, manual text input, wrap-up answers.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedTransaction:
    amount: float
    merchant: str
    confidence: float
    raw: str


# Pattern matching Vietnamese số tiền
AMOUNT_PATTERNS = [
    # "45k", "150k"
    (re.compile(r"(\d+(?:\.\d+)?)\s*k\b", re.IGNORECASE), lambda m: float(m.group(1)) * 1000),
    # "1.5tr", "2tr", "1.5 triệu"
    (re.compile(r"(\d+(?:\.\d+)?)\s*(tr|triệu|trieu)\b", re.IGNORECASE), lambda m: float(m.group(1)) * 1_000_000),
    # "500 nghìn", "500 ngàn"
    (re.compile(r"(\d+(?:\.\d+)?)\s*(nghìn|nghin|ngàn|ngan)\b", re.IGNORECASE), lambda m: float(m.group(1)) * 1000),
    # Full number "45000", "150000"
    (re.compile(r"\b(\d{4,})\b"), lambda m: float(m.group(1))),
]


def parse_transaction_text(text: str) -> Optional[ParsedTransaction]:
    """
    Parse câu Vietnamese → (amount, merchant).
    
    Examples:
      "45k phở" → (45000, "phở")
      "ăn trưa 150k" → (150000, "ăn trưa")
      "1.5tr mua giày" → (1500000, "mua giày")
      "grab 80 nghìn" → (80000, "grab")
    """
    text = text.strip()
    if not text:
        return None
    
    # Find amount
    amount = None
    amount_span = None
    for pattern, converter in AMOUNT_PATTERNS:
        match = pattern.search(text)
        if match:
            amount = converter(match)
            amount_span = match.span()
            break
    
    if not amount:
        return None
    
    # Amount sane check
    if amount < 1000 or amount > 1_000_000_000:  # <1k or >1 tỷ
        return None
    
    # Extract merchant (remaining text)
    before = text[:amount_span[0]].strip()
    after = text[amount_span[1]:].strip()
    
    # Clean common words
    merchant_text = f"{before} {after}".strip()
    merchant_text = re.sub(r"^(vừa|đã|vua|da)\s+", "", merchant_text, flags=re.IGNORECASE)
    merchant_text = re.sub(r"^(ăn|an|uống|uong|mua|đi|di)\s+", r"\1 ", merchant_text, flags=re.IGNORECASE)
    
    if not merchant_text:
        return None
    
    confidence = 0.9 if (before and after) else 0.75
    
    return ParsedTransaction(
        amount=amount,
        merchant=merchant_text.strip(),
        confidence=confidence,
        raw=text,
    )
```

### File: `app/capture/voice/context_resolver.py`

Handle "như hôm qua", "quán cũ":

```python
"""
Resolve contextual references in voice input.
"""

from app.services.transaction_service import TransactionService


async def resolve_context(text: str, user_id: int) -> dict | None:
    """
    Check text có reference context nào không.
    Return pre-filled fields nếu có.
    """
    text_lower = text.lower()
    
    # "như hôm qua" / "như ngày hôm qua"
    if "như hôm qua" in text_lower or "nhu hom qua" in text_lower:
        tx_service = TransactionService()
        last_tx = await tx_service.get_latest_yesterday(user_id)
        if last_tx:
            return {
                "merchant": last_tx.merchant,
                "category_code": last_tx.category_code,
                # Nhưng amount vẫn phải từ câu này
            }
    
    # "quán cũ" / "chỗ quen"
    if "quán cũ" in text_lower or "chỗ quen" in text_lower or "chỗ cũ" in text_lower:
        tx_service = TransactionService()
        # Lấy merchant user hay đi nhất
        top_merchant = await tx_service.get_most_frequent_merchant(user_id, days=30)
        if top_merchant:
            return {
                "merchant": top_merchant,
            }
    
    return None
```

### File: `app/bot/handlers/voice.py`

```python
from telegram import Update
from telegram.ext import ContextTypes

from app.capture.voice.whisper_client import transcribe_vietnamese
from app.capture.voice.nlu_parser import parse_transaction_text
from app.capture.voice.context_resolver import resolve_context


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    voice = update.message.voice
    
    processing = await update.message.reply_text("🎤 Đang nghe...")
    
    try:
        # Download audio
        audio_file = await voice.get_file()
        audio_bytes = await audio_file.download_as_bytearray()
        
        # Transcribe
        transcript = await transcribe_vietnamese(bytes(audio_bytes))
        
        if not transcript:
            await processing.edit_text("Mình chưa nghe rõ 😅 Nói lại giúp mình nhé?")
            return
        
        # Show transcript
        await processing.edit_text(f"🎤 Mình nghe: *{transcript}*\nĐang xử lý...")
        
        # Parse
        parsed = parse_transaction_text(transcript)
        
        if not parsed:
            await processing.edit_text(
                f"🎤 Mình nghe: *{transcript}*\n\n"
                "Nhưng chưa thấy rõ số tiền. Nói lại giúp mình? Ví dụ 'phở 45k' nhé"
            )
            return
        
        # Try resolve context
        context_data = await resolve_context(transcript, user_id)
        if context_data:
            # Override với context data
            for k, v in context_data.items():
                if k != "amount":
                    setattr(parsed, k, v)
        
        # Save via CaptureService
        from app.services.capture_service import CaptureService
        capture = CaptureService()
        result = await capture.process_voice(user_id, parsed, transcript)
        
        if result.success:
            from app.bot.formatters.templates import format_transaction_confirmation
            from app.bot.keyboards.transaction_keyboard import transaction_actions_keyboard
            
            text = format_transaction_confirmation(
                merchant=result.transaction.merchant,
                amount=result.transaction.amount,
                category_code=result.transaction.category_code,
            )
            text = f"🎤 Từ voice:\n\n{text}"
            
            await processing.edit_text(
                text=text,
                reply_markup=transaction_actions_keyboard(result.transaction.id),
            )
    except Exception as e:
        await processing.edit_text("Có lỗi xử lý voice 😔")
        print(f"Voice error: {e}")
```

---

## ✅ Checklist Cuối Tuần 5

- [ ] Default categorizer rules YAML — ít nhất 100 merchants VN phổ biến
- [ ] `MerchantRule` model + migration
- [ ] Rule engine với 3-layer fallback (user → default → LLM)
- [ ] LLM fallback via DeepSeek
- [ ] Learning service: record_correction hoạt động
- [ ] Integration: Phase 1's "Đổi danh mục" trigger learning
- [ ] Voice: Whisper transcribe tiếng Việt
- [ ] NLU parser cho "45k phở", "1.5tr quần áo"
- [ ] Context resolver cho "như hôm qua", "quán cũ"
- [ ] Test voice với giọng Bắc + Nam + Trung
- [ ] Test categorizer accuracy sau 50 corrections: >80%

---

# 📍 TUẦN 6: Location Capture (Optional) + Polish + Metrics

> **Đây là tuần "có thì tốt, không có cũng OK".** Location capture có value nhưng privacy implications lớn. Nếu time tight, skip tuần này, tập trung polish.

## 6.1 — Location Capture (Opt-in Only)

### Privacy-first design principles:

1. **Default OFF** — không bao giờ enable by default
2. **Opt-in 2 lần**: Bật trong settings + cấp permission browser
3. **Explicit transparency**: "Bot biết bạn đang ở đâu" — không ngụy trang
4. **Easy toggle**: Tắt bất cứ lúc nào, data cũ delete sau 30 ngày
5. **No passive tracking**: User phải actively "check in" qua Mini App

### Mini App implementation

```javascript
// miniapp/static/js/location.js

async function requestLocation() {
    if (!navigator.geolocation) {
        alert("Trình duyệt không hỗ trợ location");
        return;
    }
    
    // Confirmation trước khi request
    const confirmed = await showConfirmDialog(
        "Bot sẽ biết bạn đang ở đâu để gợi ý ghi giao dịch. " +
        "Không track liên tục — chỉ check khi bạn tap nút này."
    );
    
    if (!confirmed) return;
    
    navigator.geolocation.getCurrentPosition(
        async (position) => {
            // Send to backend
            const response = await fetch('/miniapp/api/location/checkin', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': tg.initData,
                },
                body: JSON.stringify({
                    lat: position.coords.latitude,
                    lng: position.coords.longitude,
                }),
            });
            
            const data = await response.json();
            
            if (data.places && data.places.length) {
                // Hiện list nearby commercial places
                showPlacePicker(data.places);
            } else {
                alert("Không tìm thấy quán/cửa hàng gần đây");
            }
        },
        (error) => {
            alert("Không lấy được location: " + error.message);
        }
    );
}
```

### Backend: Google Places integration

```python
# app/capture/location/places_client.py

import httpx
from app.config import settings


async def nearby_commercial_places(lat: float, lng: float, radius: int = 100) -> list:
    """Query Google Places API for nearby commercial locations."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
            params={
                "location": f"{lat},{lng}",
                "radius": radius,
                "type": "restaurant|cafe|supermarket|store|bar",
                "key": settings.GOOGLE_PLACES_API_KEY,
            },
        )
        data = response.json()
        
        return [
            {
                "name": place["name"],
                "type": place.get("types", [""])[0],
                "address": place.get("vicinity", ""),
                "place_id": place["place_id"],
            }
            for place in data.get("results", [])[:5]
        ]
```

---

## 6.2 — Metrics Dashboard

Track capture efficiency:

```python
# app/miniapp/routes.py - add endpoint

@router.get("/api/capture-stats")
async def capture_stats(auth = Depends(require_miniapp_auth)):
    """
    % giao dịch per source, auto vs manual ratio.
    """
    user_id = auth["user_id"]
    
    # Last 30 days
    stats = await transaction_service.get_source_breakdown(user_id, days=30)
    
    return {
        "total_transactions": stats["total"],
        "auto_captured_pct": stats["auto_pct"],
        "by_source": {
            "manual": stats["manual_count"],
            "sms": stats["sms_count"],
            "ocr": stats["ocr_count"],
            "voice": stats["voice_count"],
            "wrap_up": stats["wrap_up_count"],
            "location": stats["location_count"],
        },
        "categorizer_accuracy": stats["categorizer_accuracy_pct"],
        # % correct on first try (không bị user sửa)
    }
```

Hiện trong Mini App settings page — user thấy rõ hệ thống đang giúp họ thế nào.

---

## 6.3 — Polish Checklist

### Performance
- [ ] SMS parsing <50ms per message
- [ ] OCR call <3s end-to-end
- [ ] Voice transcribe <4s end-to-end
- [ ] All handlers handle errors gracefully (no 500 to user)

### Security
- [ ] Raw SMS encrypted at rest
- [ ] Audit log cho mọi captured transaction
- [ ] Bot token + chat_id transmit qua HTTPS only
- [ ] API keys trong env vars, không commit

### User Experience
- [ ] Mọi source transaction đều có inline buttons edit
- [ ] Category changes trigger learning
- [ ] Low confidence captures được user confirm trước khi lưu
- [ ] Error messages ấm áp, không technical

### Testing
- [ ] Integration test: full flow từ SMS → DB → bot message
- [ ] Load test: 100 concurrent SMS forwards không fail
- [ ] Edge cases: malformed SMS, oversized images, silent voice

---

## ✅ Exit Criteria Phase 3

Chỉ sang Phase 4 khi:

- [ ] **>85% transaction auto-captured** cho Android users active
- [ ] **>60% auto-captured** cho iPhone users active
- [ ] **Categorizer accuracy >80%** sau 30 corrections (lần sau tự đúng)
- [ ] **Zero security incidents** (no SMS data leak)
- [ ] **Zero data loss**: mọi raw SMS đều save được, ngay cả khi parse fail
- [ ] Friends beta test: 10+ users, không có complaint về privacy
- [ ] Metrics: D7 retention tăng ít nhất 10% so với cuối Phase 2

---

# 🚧 Bẫy Lớn Của Phase 3

## 1. Over-Promise Auto-Capture
Đừng claim "100% tự động". Thực tế là ~90% cho Android, ~60% cho iPhone. User sẽ thất vọng nếu bạn hứa quá.

## 2. Ignore iPhone Users
30-40% user target dùng iPhone. Nếu bạn chỉ làm Android SMS forward → lose half market.

## 3. LLM Cost Explosion
Nếu categorize mọi giao dịch qua LLM → cost $$$. Rule-based FIRST, LLM fallback, cache aggressive.

## 4. Privacy Nightmare
Một bug để lộ SMS của user = app chết ngay. **Encrypt at rest, audit log, principle of least privilege.**

## 5. Ignore Learning Loop
Nếu user sửa category 10 lần mà bot vẫn đoán sai → dùng cảm giác "bot ngu". Learning service MUST work từ transaction đầu tiên.

## 6. Không Handle Duplicates
User forward cùng 1 SMS 2 lần → 2 giao dịch trong DB. Duplicate detection là MUST HAVE.

## 7. Timezone Bugs
SMS có timestamp, user có timezone. Nếu parse sai, giao dịch hôm nay thành hôm qua → user confused.

## 8. Không Graceful Degradation
Claude API down → bot không phản hồi ảnh → user bực. Cần fallback: "OCR tạm thời không work, bạn gõ tay giúp mình?"

---

# 📚 Tài Liệu Tham Khảo

- Claude Vision API docs: https://docs.claude.com/en/docs/build-with-claude/vision
- OpenAI Whisper: https://platform.openai.com/docs/guides/speech-to-text
- SMS Forwarder app: Play Store
- Apple Shortcuts docs: https://support.apple.com/guide/shortcuts/
- Google Places API: https://developers.google.com/maps/documentation/places/web-service/overview

---

# 🎉 Next Step

Sau Phase 3, bạn có hệ thống capture mạnh. Dữ liệu quality cao. **Đây là lúc lý tưởng để làm Phase 4 — Behavioral Finance Engine** — vì bạn có đủ data để detect patterns có nghĩa.

Tuy nhiên, **cân nhắc đặt 2-4 tuần "stability break"** trước Phase 4:
- Fix bugs user report
- Optimize performance
- Gather user feedback sâu
- Có thể làm Phase 5 Web Dashboard trước nếu feedback nói muốn

Phase 3 là phase KHÓ NHẤT về technical. Nếu xong được, bạn đã có sản phẩm vượt xa mọi finance app VN hiện tại về automation. 

**Luôn nhớ nguyên tắc: Conversational correction > Perfect parsing. User sửa 1 tap quan trọng hơn parse 100% đúng. 💚**

**Good luck với Phase 3! 🚀**
