# Phase 2 — Làm Khách Hàng Cảm Thấy Được Quan Tâm (Chi Tiết Triển Khai)

> **Thời gian ước tính:** 2-3 tuần
> **Mục tiêu cuối Phase:** User cảm thấy bot "hiểu mình" — có mối quan hệ, không phải tool. Retention D7 tăng từ ~30% lên ~50%+.
> **Điều kiện "Done":** Friends test nói câu như *"Bot này dễ thương ghê"*, *"Cảm giác như có người thật theo dõi mình"*, *"Tui thấy buồn cười mà ấm"*.

> **Prerequisites từ Phase 1:** Rich messages, inline buttons, Mini App đã hoạt động. Analytics đã track events cơ bản. Nếu chưa xong Phase 1 đừng nhảy sang Phase 2 — personality cần "vỏ đẹp" mới thể hiện được.

---

## 📅 Phân Bổ Thời Gian 3 Tuần

| Tuần | Nội dung chính | Deliverable |
|------|---------------|-------------|
| **Tuần 1** | Onboarding 3 phút + User profile | User mới gặp bot có "wow moment", tên + goal được lưu |
| **Tuần 2** | Memory Moments + Empathy Engine | Bot gửi tin nhắn kỷ niệm, phản hồi cảm xúc đúng ngữ cảnh |
| **Tuần 3** | Surprise & Delight + Polish + Testing | Fun facts, seasonal content, streak system, beta feedback |

**Lưu ý về thời gian:** Phase này có ít code hơn Phase 1 nhưng nhiều **content writing** — viết 50+ tin nhắn mẫu. Đừng underestimate phần này, nó quyết định chất lượng UX.

---

# 🗂️ Cấu Trúc Thư Mục Mở Rộng

Tiếp tục cấu trúc Phase 1, thêm các module mới:

```
finance_assistant/
├── app/
│   ├── bot/
│   │   ├── handlers/
│   │   │   ├── onboarding.py           # ⭐ NEW
│   │   │   └── ...
│   │   ├── formatters/
│   │   │   ├── templates.py            # Mở rộng
│   │   │   └── empathy_templates.py    # ⭐ NEW
│   │   └── personality/                # ⭐ NEW - Linh hồn bot
│   │       ├── __init__.py
│   │       ├── onboarding_flow.py
│   │       ├── memory_moments.py
│   │       ├── empathy_engine.py
│   │       ├── seasonal_content.py
│   │       └── fun_facts.py
│   │
│   ├── models/
│   │   ├── user.py                     # Thêm columns
│   │   ├── user_milestone.py           # ⭐ NEW
│   │   ├── user_event.py               # ⭐ NEW (dùng cho empathy triggers)
│   │   └── streak.py                   # ⭐ NEW
│   │
│   ├── services/
│   │   ├── onboarding_service.py       # ⭐ NEW
│   │   ├── milestone_service.py        # ⭐ NEW
│   │   ├── empathy_service.py          # ⭐ NEW
│   │   └── streak_service.py           # ⭐ NEW
│   │
│   └── scheduled/                      # ⭐ NEW - Scheduled jobs
│       ├── __init__.py
│       ├── check_milestones.py         # Chạy 8h sáng
│       ├── check_empathy_triggers.py   # Chạy mỗi giờ
│       ├── weekly_fun_facts.py         # Chạy CN 19h
│       └── seasonal_notifier.py        # Chạy 8h sáng
│
├── content/                            # ⭐ NEW - Content Vietnamese
│   ├── milestone_messages.yaml
│   ├── empathy_messages.yaml
│   ├── seasonal_calendar.yaml
│   └── fun_fact_templates.yaml
│
├── alembic/versions/
│   ├── xxx_add_onboarding_columns.py   # Migration mới
│   ├── xxx_create_user_milestones.py
│   ├── xxx_create_user_events.py
│   └── xxx_create_streaks.py
```

**⭐ = folder/file mới trong Phase 2**

**Quyết định quan trọng:** Content (tin nhắn mẫu) nên tách ra **file YAML riêng**, không hardcode trong Python. Lý do:
- Dễ edit mà không cần deploy
- Dễ thuê người viết content chỉnh sửa
- Dễ localize sau này (thêm tiếng Anh, v.v.)
- Dễ A/B test (swap file)

---

# 🎯 TUẦN 1: Onboarding 3 Phút + User Profile

## 1.1 — Database Migrations

### File: `alembic/versions/xxx_add_onboarding_columns.py`

Trước khi code logic, update schema trước:

```python
"""Add onboarding columns to users table

Revision ID: xxx
"""
from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('users', sa.Column('display_name', sa.String(50), nullable=True))
    op.add_column('users', sa.Column('primary_goal', sa.String(30), nullable=True))
    op.add_column('users', sa.Column('onboarding_step', sa.Integer, default=0, nullable=False))
    op.add_column('users', sa.Column('onboarding_completed_at', sa.DateTime, nullable=True))
    op.add_column('users', sa.Column('onboarding_skipped', sa.Boolean, default=False))
    
    # Index cho query user chưa hoàn thành onboarding
    op.create_index('idx_users_onboarding', 'users', ['onboarding_step'])


def downgrade():
    op.drop_index('idx_users_onboarding', 'users')
    op.drop_column('users', 'onboarding_skipped')
    op.drop_column('users', 'onboarding_completed_at')
    op.drop_column('users', 'onboarding_step')
    op.drop_column('users', 'primary_goal')
    op.drop_column('users', 'display_name')
```

### File: `app/models/user.py` (update)

```python
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from app.database import Base


class User(Base):
    __tablename__ = "users"
    
    # ... existing columns
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # NEW in Phase 2
    display_name = Column(String(50), nullable=True)
    primary_goal = Column(String(30), nullable=True)  # "save_more", "understand", "goal", "less_stress"
    onboarding_step = Column(Integer, default=0, nullable=False)
    onboarding_completed_at = Column(DateTime, nullable=True)
    onboarding_skipped = Column(Boolean, default=False)
    
    @property
    def is_onboarded(self) -> bool:
        return self.onboarding_completed_at is not None or self.onboarding_skipped
    
    def get_greeting_name(self) -> str:
        """Tên để gọi user — fallback nếu chưa có display_name."""
        return self.display_name or "bạn"
```

---

## 1.2 — Onboarding State Machine

### File: `app/bot/personality/onboarding_flow.py`

State machine đơn giản, mỗi step độc lập:

```python
"""
Onboarding flow — 5 steps, 3 phút.
Mỗi step có: prompt message, input handler, next step logic.
"""

from enum import IntEnum
from dataclasses import dataclass
from typing import Callable


class OnboardingStep(IntEnum):
    NOT_STARTED = 0
    WELCOME = 1           # Đã gửi lời chào
    ASKING_NAME = 2       # Đang hỏi tên
    ASKING_GOAL = 3       # Đang hỏi mục tiêu
    FIRST_TRANSACTION = 4 # Hướng dẫn ghi giao dịch đầu
    COMPLETED = 5


PRIMARY_GOALS = {
    "save_more": "💰 Tiết kiệm nhiều hơn",
    "understand": "📊 Hiểu mình tiêu vào đâu",
    "reach_goal": "🎯 Đạt mục tiêu cụ thể",
    "less_stress": "🧘 Bớt stress về tiền",
}
```

### File: `app/bot/handlers/onboarding.py`

```python
"""
Onboarding handlers — xử lý từng step của flow.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from app.bot.personality.onboarding_flow import OnboardingStep, PRIMARY_GOALS
from app.services.onboarding_service import OnboardingService
from app.services.user_service import UserService


async def handle_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Xử lý /start. 
    - User mới: bắt đầu onboarding
    - User cũ chưa xong: resume
    - User cũ đã xong: gửi welcome back
    """
    telegram_id = update.effective_user.id
    user_service = UserService()
    user = await user_service.get_or_create(telegram_id=telegram_id)
    
    if user.is_onboarded:
        # User đã onboarded rồi
        await send_welcome_back(update, user)
        return
    
    # Bắt đầu hoặc tiếp tục onboarding
    onboarding = OnboardingService()
    await onboarding.resume_or_start(update, user)


async def step_1_welcome(update: Update, user):
    """Step 1: Lời chào ấm áp."""
    text = """👋 Chào bạn!

Mình là Xu — trợ lý tài chính của bạn.
Mình không chỉ ghi chép — mình hiểu bạn.

Trước khi bắt đầu, cho mình hỏi 2 câu nhẹ nhé? 
(Mất 1 phút thôi, nhưng giúp mình phục vụ bạn tốt hơn nhiều!)"""
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✨ Bắt đầu", callback_data="onboarding:start"),
        InlineKeyboardButton("⏭ Bỏ qua", callback_data="onboarding:skip"),
    ]])
    
    await update.effective_message.reply_text(text, reply_markup=keyboard)
    
    # Update state
    service = OnboardingService()
    await service.set_step(user.id, OnboardingStep.WELCOME)


async def step_2_ask_name(update: Update, user):
    """Step 2: Hỏi tên user muốn được gọi."""
    text = """Tuyệt! 

Bạn muốn mình gọi bạn là gì? 😊
(Tên, nickname, hay gì cũng được — miễn là bạn thấy thoải mái)"""
    
    await update.effective_message.reply_text(text)
    
    service = OnboardingService()
    await service.set_step(user.id, OnboardingStep.ASKING_NAME)


async def handle_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User gửi tin nhắn text khi đang ở step ASKING_NAME.
    Validate + lưu display_name.
    """
    user_service = UserService()
    user = await user_service.get_by_telegram_id(update.effective_user.id)
    
    if user.onboarding_step != OnboardingStep.ASKING_NAME:
        return  # Không phải step này, bỏ qua
    
    name = update.message.text.strip()
    
    # Validate
    if len(name) > 50:
        await update.message.reply_text(
            "Ôi tên hơi dài quá 😅 Bạn dùng tên ngắn hơn được không?"
        )
        return
    
    if len(name) < 1:
        await update.message.reply_text("Bạn nhập tên lại giúp mình nhé 🙏")
        return
    
    # Lưu
    await user_service.update_display_name(user.id, name)
    
    # Sang step 3
    await step_3_ask_goal(update, user, name)


async def step_3_ask_goal(update: Update, user, name: str):
    """Step 3: Hỏi mục tiêu chính (buttons)."""
    text = f"""Rất vui được gặp {name}! 🌱

{name} ơi, bạn đang muốn cải thiện điều gì nhất về tài chính lúc này?

(Chọn 1 cái cũng được, không có đáp án "đúng" đâu)"""
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"onboarding:goal:{code}")]
        for code, label in PRIMARY_GOALS.items()
    ])
    
    await update.effective_message.reply_text(text, reply_markup=keyboard)
    
    service = OnboardingService()
    await service.set_step(user.id, OnboardingStep.ASKING_GOAL)


async def handle_goal_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User tap button chọn mục tiêu."""
    query = update.callback_query
    await query.answer()
    
    # Parse callback_data: "onboarding:goal:save_more"
    _, _, goal_code = query.data.split(":")
    
    user_service = UserService()
    user = await user_service.get_by_telegram_id(query.from_user.id)
    
    await user_service.update_primary_goal(user.id, goal_code)
    
    # Customize phản hồi theo goal
    goal_responses = {
        "save_more": "Mình sẽ giúp bạn nhìn rõ chi tiêu và tìm chỗ tiết kiệm được 💰",
        "understand": "Tuyệt vời! Mình sẽ giúp bạn thấy rõ tiền đi đâu, không còn mơ hồ nữa 📊",
        "reach_goal": "Mục tiêu rõ ràng là bước đầu quan trọng nhất! Mình sẽ đồng hành cùng bạn 🎯",
        "less_stress": "Mình hiểu cảm giác đó. Chúng ta sẽ làm từng bước nhỏ, không áp lực 🧘",
    }
    
    response = goal_responses.get(goal_code, "Cảm ơn bạn đã chia sẻ!")
    await query.edit_message_text(f"{response}\n\n...")
    
    # Sang step 4
    await step_4_first_transaction(update, user)


async def step_4_first_transaction(update: Update, user):
    """Step 4: Hướng dẫn ghi giao dịch đầu tiên."""
    text = f"""Giờ mình thử ngay nhé {user.display_name}!

Bạn hôm nay đã chi gì rồi không? 
Gõ số tiền và mô tả ngắn, ví dụ:

💬 "45k phở"
💬 "120k xăng"  
💬 "35000 cafe"

Thử đi, mình sẽ ghi lại cho bạn! 👇"""
    
    await update.effective_message.reply_text(text)
    
    service = OnboardingService()
    await service.set_step(user.id, OnboardingStep.FIRST_TRANSACTION)


async def step_5_aha_moment(update: Update, user, transaction):
    """
    Step 5 được gọi SAU KHI user đã ghi giao dịch đầu tiên thành công.
    Hook vào transaction handler.
    """
    text = f"""🎉 Tuyệt vời {user.display_name}!

Đó là giao dịch đầu tiên của bạn với mình.
Từ giờ, bạn có 3 cách để ghi chép — cái nào tiện thì dùng:

📝 Gõ text: như vừa rồi
📸 Gửi ảnh hóa đơn: mình đọc được  
🎤 Gửi voice: mình hiểu luôn

Hoặc tap /help bất cứ lúc nào để xem mẹo hay.
Sẵn sàng đi cùng mình chưa? 💪"""
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🚀 Bắt đầu", callback_data="onboarding:complete"),
    ]])
    
    await update.effective_message.reply_text(text, reply_markup=keyboard)


async def handle_complete_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User tap "Bắt đầu" ở step cuối."""
    query = update.callback_query
    await query.answer("🎊 Chào mừng!")
    
    user_service = UserService()
    user = await user_service.get_by_telegram_id(query.from_user.id)
    
    onboarding = OnboardingService()
    await onboarding.mark_completed(user.id)
    
    # Track analytics
    from app.analytics import track, Event
    from datetime import datetime
    await track(Event(
        user_id=user.id,
        event_type="onboarding_completed",
        properties={"duration_seconds": (datetime.utcnow() - user.created_at).total_seconds()},
        timestamp=datetime.utcnow(),
    ))
    
    await query.edit_message_text(
        f"Xong rồi! Từ giờ mình luôn ở đây 💚\n\nGhi giao dịch đầu tiên thật sự nào!"
    )
```

---

## 1.3 — Onboarding Service

### File: `app/services/onboarding_service.py`

Tách business logic ra khỏi handlers:

```python
from datetime import datetime
from app.bot.personality.onboarding_flow import OnboardingStep
from app.models.user import User
from app.database import get_session


class OnboardingService:
    async def resume_or_start(self, update, user: User):
        """
        Entry point — quyết định user đang ở step nào và xử lý tiếp.
        """
        step = OnboardingStep(user.onboarding_step)
        
        from app.bot.handlers.onboarding import (
            step_1_welcome, step_2_ask_name, 
            step_3_ask_goal, step_4_first_transaction,
        )
        
        if step == OnboardingStep.NOT_STARTED:
            await step_1_welcome(update, user)
        elif step == OnboardingStep.WELCOME:
            # User gõ /start lại sau step 1
            await step_2_ask_name(update, user)
        elif step == OnboardingStep.ASKING_NAME:
            # Nhắc user nhập tên
            await update.effective_message.reply_text(
                "Bạn muốn mình gọi bạn là gì nhỉ? 😊"
            )
        elif step == OnboardingStep.ASKING_GOAL:
            await step_3_ask_goal(update, user, user.display_name or "bạn")
        elif step == OnboardingStep.FIRST_TRANSACTION:
            await step_4_first_transaction(update, user)
    
    async def set_step(self, user_id: int, step: OnboardingStep):
        async with get_session() as session:
            user = await session.get(User, user_id)
            user.onboarding_step = int(step)
            await session.commit()
    
    async def mark_completed(self, user_id: int):
        async with get_session() as session:
            user = await session.get(User, user_id)
            user.onboarding_step = int(OnboardingStep.COMPLETED)
            user.onboarding_completed_at = datetime.utcnow()
            await session.commit()
    
    async def mark_skipped(self, user_id: int):
        async with get_session() as session:
            user = await session.get(User, user_id)
            user.onboarding_skipped = True
            await session.commit()
    
    async def is_in_first_transaction_step(self, user_id: int) -> bool:
        async with get_session() as session:
            user = await session.get(User, user_id)
            return user.onboarding_step == OnboardingStep.FIRST_TRANSACTION
```

---

## 1.4 — Integration Points

### Các điểm cần hook vào code Phase 1:

**1. Update `handlers/commands.py` cho `/start`:**
```python
from app.bot.handlers.onboarding import handle_start_command

# Thay handler cũ bằng handler mới
application.add_handler(CommandHandler("start", handle_start_command))
```

**2. Update message handler để route text theo step:**
```python
async def handle_text_message(update, context):
    user = await user_service.get_by_telegram_id(update.effective_user.id)
    
    # Nếu đang trong onboarding step ASKING_NAME
    if user.onboarding_step == OnboardingStep.ASKING_NAME:
        from app.bot.handlers.onboarding import handle_name_input
        return await handle_name_input(update, context)
    
    # Default: xử lý như giao dịch
    await handle_transaction_text(update, context)
```

**3. Hook step 5 vào transaction handler:**
```python
async def handle_new_transaction(update, context, parsed_data):
    # ... existing code ghi giao dịch ...
    
    # Check nếu đây là giao dịch đầu trong onboarding
    onboarding = OnboardingService()
    if await onboarding.is_in_first_transaction_step(user.id):
        await step_5_aha_moment(update, user, transaction)
```

---

## ✅ Checklist Cuối Tuần 1

- [ ] Migration `add_onboarding_columns` applied
- [ ] Model `User` có đủ columns mới
- [ ] State machine `OnboardingStep` định nghĩa rõ ràng
- [ ] 5 step handlers implement đầy đủ
- [ ] `/start` route tới onboarding đúng
- [ ] Text message khi `onboarding_step = ASKING_NAME` xử lý riêng
- [ ] Transaction đầu tiên trigger step 5
- [ ] Analytics event `onboarding_started`, `onboarding_step_X_completed`, `onboarding_completed`, `onboarding_skipped` được track
- [ ] Tự test flow end-to-end trên bot dev
- [ ] Edge case: user gõ `/start` lại giữa chừng → resume đúng step

---

# 💝 TUẦN 2: Memory Moments + Empathy Engine

## 2.1 — Milestone Database

### File: `alembic/versions/xxx_create_user_milestones.py`

```python
def upgrade():
    op.create_table(
        'user_milestones',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('milestone_type', sa.String(50), nullable=False),
        sa.Column('achieved_at', sa.DateTime, default=sa.func.now(), nullable=False),
        sa.Column('celebrated_at', sa.DateTime, nullable=True),  # Đã gửi tin nhắn chưa
        sa.Column('metadata', sa.JSON, nullable=True),  # Context: số liệu, mô tả
    )
    op.create_index('idx_milestones_user_type', 'user_milestones', ['user_id', 'milestone_type'])
    op.create_index('idx_milestones_not_celebrated', 'user_milestones', ['celebrated_at'])
```

### File: `app/models/user_milestone.py`

```python
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from app.database import Base


class UserMilestone(Base):
    __tablename__ = "user_milestones"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    milestone_type = Column(String(50), nullable=False)
    achieved_at = Column(DateTime, nullable=False)
    celebrated_at = Column(DateTime, nullable=True)
    metadata = Column(JSON, nullable=True)


# Milestone types (constants để dễ reference)
class MilestoneType:
    # Time-based
    FIRST_TRANSACTION = "first_transaction"
    DAYS_7 = "days_7"
    DAYS_30 = "days_30"
    DAYS_100 = "days_100"
    DAYS_365 = "days_365"
    
    # Behavior-based
    FIRST_BUDGET_SET = "first_budget_set"
    FIRST_CATEGORY_CHANGE = "first_category_change"
    FIRST_VOICE_INPUT = "first_voice_input"
    FIRST_PHOTO_INPUT = "first_photo_input"
    
    # Financial
    SAVE_10_PERCENT_MONTHLY = "save_10_percent_monthly"
    SAVE_20_PERCENT_MONTHLY = "save_20_percent_monthly"
    SAVINGS_1M = "savings_1m"    # Tiết kiệm 1 triệu
    SAVINGS_5M = "savings_5m"
    SAVINGS_10M = "savings_10m"
    SAVINGS_50M = "savings_50m"
    
    # Streak
    STREAK_7 = "streak_7"
    STREAK_30 = "streak_30"
    STREAK_100 = "streak_100"
```

---

## 2.2 — Milestone Content (YAML)

### File: `content/milestone_messages.yaml`

**Lý do tách YAML:** Content là thứ sẽ sửa nhiều nhất. Không cần deploy khi chỉnh văn.

```yaml
# Milestone messages - Vietnamese content
# Placeholder: {name}, {days}, {count}, {amount}, {goal}

first_transaction:
  - "🎉 Giao dịch đầu tiên! Chào mừng {name} đến với hành trình hiểu chi tiêu của mình.\n\nMỗi giao dịch bạn ghi là một mảnh ghép giúp bức tranh tài chính rõ ràng hơn 🌱"

days_7:
  - "✨ Một tuần rồi nhỉ {name}!\n\nBạn đã ghi {count} giao dịch trong 7 ngày qua — con số này cho thấy bạn thật sự nghiêm túc với tài chính của mình. Đừng xem thường điều đó 💪\n\nBây giờ mình đã bắt đầu hiểu được vài điều về bạn rồi đấy. Cuối tuần mình sẽ gửi tóm tắt đầu tiên nhé!"
  - "🌱 7 ngày! {name} biết không, chỉ 30% người mới bắt đầu vượt qua được mốc này đấy.\n\nBạn đang làm tốt hơn bạn tưởng nhiều 💚"

days_30:
  - "🎊 Tròn 1 tháng rồi {name}!\n\nCùng nhìn lại nhé:\n• {count} giao dịch được ghi\n• {amount} tổng chi tiêu\n• {goal_progress}\n\n80% người bỏ cuộc trong 30 ngày đầu — bạn đã vượt qua. Đây là bước ngoặt đó 🚀"

days_100:
  - "💯 MỘT TRĂM NGÀY {name}!\n\nThật sự... không nhiều người đi được đến đây. Bạn đã thay đổi mối quan hệ với tiền của mình.\n\nMình ở đây, vẫn theo dõi, vẫn học hỏi cùng bạn 🌳"

days_365:
  - "🎂 Tròn 1 năm rồi {name}!\n\nMột hành trình dài, và mình là người chứng kiến. Cảm ơn bạn đã tin tưởng mình 💚\n\nCuối tuần mình gửi báo cáo năm đặc biệt cho bạn nhé?"

save_10_percent_monthly:
  - "🌟 Ồ! Lần đầu tiên {name} tiết kiệm được 10% thu nhập trong tháng!\n\nBạn biết điều này ý nghĩa gì không? Đây là con số mà các chuyên gia tài chính xem là 'bắt đầu ổn'. Bạn đã qua được ngưỡng khó nhất — ngưỡng 'bắt đầu' 🎯"

savings_1m:
  - "💰 1 triệu đầu tiên!\n\nĐừng xem thường {name} ạ. 1 triệu này khác với 1 triệu ở tài khoản lương — đây là 1 triệu bạn chủ động giữ lại. Nó có sức mạnh khác 💪"

savings_10m:
  - "🏆 10 triệu tiết kiệm!\n\n{name} ơi, mốc này đáng để kỷ niệm. Nếu để yên ở tài khoản tiết kiệm lãi 6%/năm, 10 năm sau bạn sẽ có ~17.9 triệu. Nếu đầu tư tốt hơn... còn nhiều hơn 📈\n\nMình sẽ giúp bạn suy nghĩ về bước tiếp theo nhé?"

streak_7:
  - "🔥 7 ngày liên tục ghi chép!\n\nHabit đang hình thành rồi đó {name}. Khoa học nói 21 ngày là bắt đầu tự động. Bạn đã đi 1/3 chặng đường!"

streak_30:
  - "⚡ 30 ngày streak!\n\nBạn biết không {name}, thói quen này giờ đã là một phần của bạn rồi. Tiếp tục nhé 🌟"

streak_100:
  - "👑 100 NGÀY LIÊN TỤC!\n\nMình không biết nói gì ngoài: bạn xuất sắc {name}.\nBạn là top 1% users của mình đó 🙌"
```

---

## 2.3 — Milestone Service

### File: `app/services/milestone_service.py`

```python
import yaml
import random
from datetime import datetime, timedelta
from pathlib import Path

from app.models.user_milestone import UserMilestone, MilestoneType
from app.database import get_session


class MilestoneService:
    def __init__(self):
        self._messages = self._load_messages()
    
    def _load_messages(self) -> dict:
        path = Path(__file__).parent.parent.parent / "content" / "milestone_messages.yaml"
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    async def detect_and_record(self, user_id: int) -> list[UserMilestone]:
        """
        Chạy tất cả rules detection, record các milestone mới.
        Return list milestone chưa celebrate.
        """
        new_milestones = []
        
        # Time-based milestones
        new_milestones += await self._check_time_milestones(user_id)
        
        # Savings milestones
        new_milestones += await self._check_savings_milestones(user_id)
        
        # Behavior milestones
        new_milestones += await self._check_behavior_milestones(user_id)
        
        return new_milestones
    
    async def _check_time_milestones(self, user_id: int) -> list[UserMilestone]:
        """Check các mốc thời gian (7, 30, 100, 365 ngày)."""
        async with get_session() as session:
            user = await session.get(User, user_id)
            days_since_start = (datetime.utcnow() - user.created_at).days
            
            milestones = []
            thresholds = {
                7: MilestoneType.DAYS_7,
                30: MilestoneType.DAYS_30,
                100: MilestoneType.DAYS_100,
                365: MilestoneType.DAYS_365,
            }
            
            for days, m_type in thresholds.items():
                if days_since_start >= days:
                    # Check nếu chưa có milestone này
                    existing = await self._get_milestone(session, user_id, m_type)
                    if not existing:
                        m = UserMilestone(
                            user_id=user_id,
                            milestone_type=m_type,
                            achieved_at=datetime.utcnow(),
                            metadata={"days": days_since_start},
                        )
                        session.add(m)
                        milestones.append(m)
            
            await session.commit()
            return milestones
    
    async def _check_savings_milestones(self, user_id: int) -> list[UserMilestone]:
        """Check mốc tiết kiệm: 1tr, 5tr, 10tr, 50tr."""
        # Implement similar logic
        # ... tính tổng net savings ...
        pass
    
    async def _check_behavior_milestones(self, user_id: int) -> list[UserMilestone]:
        """First time dùng voice, photo, edit category..."""
        pass
    
    async def get_celebration_message(self, milestone: UserMilestone, user) -> str:
        """Render template message với user context."""
        templates = self._messages.get(milestone.milestone_type, [])
        if not templates:
            return ""
        
        template = random.choice(templates)
        
        # Render placeholders
        context = {
            "name": user.display_name or "bạn",
            "days": milestone.metadata.get("days", 0),
            "count": milestone.metadata.get("count", 0),
            "amount": self._format_amount(milestone.metadata.get("amount", 0)),
            "goal_progress": milestone.metadata.get("goal_progress", ""),
        }
        
        return template.format(**context)
    
    async def mark_celebrated(self, milestone_id: int):
        async with get_session() as session:
            m = await session.get(UserMilestone, milestone_id)
            m.celebrated_at = datetime.utcnow()
            await session.commit()
    
    def _format_amount(self, amount: float) -> str:
        """Import format từ Phase 1."""
        from app.bot.formatters.money import format_money_full
        return format_money_full(amount)
```

---

## 2.4 — Scheduled Job: Morning Milestones Check

### File: `app/scheduled/check_milestones.py`

```python
"""
Chạy hàng ngày lúc 8h sáng.
Detect milestones mới, gửi tin nhắn chúc mừng.
"""

import asyncio
from datetime import datetime

from app.services.milestone_service import MilestoneService
from app.services.user_service import UserService
from app.bot.bot_instance import bot


async def run_daily_milestone_check():
    user_service = UserService()
    milestone_service = MilestoneService()
    
    # Lấy tất cả users active (có giao dịch 30 ngày gần đây)
    active_users = await user_service.get_active_users(days=30)
    
    for user in active_users:
        try:
            new_milestones = await milestone_service.detect_and_record(user.id)
            
            for milestone in new_milestones:
                message = await milestone_service.get_celebration_message(
                    milestone, user
                )
                
                if not message:
                    continue
                
                # Gửi qua Telegram
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=message,
                )
                
                # Mark celebrated
                await milestone_service.mark_celebrated(milestone.id)
                
                # Track
                from app.analytics import track, Event
                await track(Event(
                    user_id=user.id,
                    event_type="milestone_celebrated",
                    properties={"type": milestone.milestone_type},
                    timestamp=datetime.utcnow(),
                ))
                
                # Chống spam: không gửi >2 milestones/ngày cùng 1 user
                await asyncio.sleep(1)
        except Exception as e:
            print(f"Error checking milestones for user {user.id}: {e}")


# Setup APScheduler (hoặc cron job)
# from apscheduler.schedulers.asyncio import AsyncIOScheduler
# scheduler.add_job(run_daily_milestone_check, 'cron', hour=8, minute=0)
```

---

## 2.5 — Empathy Engine

Đây là phần khó hơn — cần logic trigger tinh tế để không sai context.

### File: `content/empathy_messages.yaml`

```yaml
# Empathy triggers - mỗi trigger có multiple variations để random

over_budget_monthly:
  conditions: "User vượt ngân sách tháng ít nhất 10%"
  cooldown_days: 14
  messages:
    - "Hmm, mình để ý tháng này bạn chi nhiều hơn một chút {name} ạ.\n\nKhông phải trách đâu — mình thấy có {context_events}, đó là những thứ đáng giá.\n\nThử cùng nhau điều chỉnh tháng sau nhé? 🌸"
    - "{name} ơi, tháng này ngân sách hơi căng một chút.\n\nMình hiểu — không phải tháng nào cũng đều. Quan trọng là chúng ta nhìn thấy được, không phải giấu nó đi 💚"

user_silent_7_days:
  conditions: "User không mở bot 7 ngày"
  cooldown_days: 14
  messages:
    - "👋 Lâu rồi không gặp {name}.\n\nMọi thứ ổn không? Nếu đang bận, bạn cứ tập trung việc của bạn nhé — mình vẫn ở đây khi bạn cần 🌱"
    - "{name} ơi, mọi thứ thế nào?\n\nMình thấy tuần này bạn im lặng. Không sao cả, mình chỉ muốn ghé chào một chút thôi 💭"

user_silent_30_days:
  conditions: "User không tương tác 30 ngày"
  cooldown_days: 60
  messages:
    - "{name} ơi... đã lâu rồi.\n\nMình không biết có phải bạn đang bận, hay mình chưa đủ hữu ích. Nếu có điều gì mình có thể làm tốt hơn, bạn nói cho mình biết được không? 🙏"

large_transaction:
  conditions: "Giao dịch > 3x median tháng của user"
  cooldown_days: 1  # Không apply cho chuyển khoản giữa tk chính user
  messages:
    - "Ồ, giao dịch lớn! {amount} là khoản đáng chú ý đó {name}.\n\nMình xếp vào đâu cho hợp lý nhỉ? Hay bạn cho mình context một chút?"
    - "Đây là khoản lớn nhất của {name} trong 30 ngày qua.\n\nNếu là khoản dự kiến (học phí, sửa xe, du lịch...) thì không có gì lo. Bạn muốn mình tạo category riêng để theo dõi không?"

weekend_high_spending:
  conditions: "Cuối tuần chi > 50% chi tuần"
  cooldown_days: 30
  messages:
    - "Haha cuối tuần mà {name} 😄 Tận hưởng thôi!\n\nMình chỉ nhắc nhẹ một chút: đây là pattern của bạn — cuối tuần thường chi nhiều hơn. Không phải xấu, chỉ là biết để tính toán ngân sách cho thực tế hơn 🌸"

payday_splurge:
  conditions: "3 ngày sau nhận lương, chi > 35% lương"
  cooldown_days: 30
  messages:
    - "Lương vừa vào được 3 ngày... {name} đã chi kha khá rồi 🫣\n\nKhông trách đâu — cảm giác có lương luôn vui. Nhưng mình có một gợi ý nhỏ: muốn 'khóa' trước {suggested_amount} vào tiết kiệm không? Còn lại tha hồ tiêu 💰"

first_saving_month:
  conditions: "User tiết kiệm dương tháng đầu tiên"
  cooldown_days: 0  # Chỉ trigger 1 lần
  messages:
    - "🌟 Tháng này bạn có tiết kiệm dương, {name}!\n\nNghĩa là thu > chi. Nghe tưởng đơn giản nhưng nhiều người không làm được đâu. Bạn đang đi đúng hướng 💪"

consecutive_over_budget:
  conditions: "Vượt ngân sách 3 tháng liên tục trong cùng category"
  cooldown_days: 60
  messages:
    - "{name} ơi, mình để ý danh mục {category} đã vượt ngân sách 3 tháng liên tục rồi.\n\nCó thể ngân sách đặt hơi thấp so với nhu cầu thực tế chăng? Chúng ta điều chỉnh cho hợp lý hơn nhé — không có gì xấu hổ cả, thực tế đang nói với chúng ta một điều gì đó 🌱"
```

---

## 2.6 — Empathy Engine Implementation

### File: `app/bot/personality/empathy_engine.py`

```python
"""
Empathy engine - rule-based system để phát hiện và phản hồi cảm xúc user.

Design:
- Mỗi trigger là 1 function riêng
- Engine chạy qua tất cả triggers theo priority
- Cooldown để tránh spam
- Random chọn variation để không nhàm
"""

import yaml
import random
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.database import get_session
from app.models.user_event import UserEvent  # Sẽ tạo bên dưới


@dataclass
class EmpathyTrigger:
    name: str
    priority: int  # Thấp hơn = cao hơn
    cooldown_days: int
    context: dict = None


class EmpathyEngine:
    def __init__(self):
        self._messages = self._load_messages()
    
    def _load_messages(self) -> dict:
        path = Path(__file__).parent.parent.parent.parent / "content" / "empathy_messages.yaml"
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    async def check_all_triggers(self, user) -> Optional[EmpathyTrigger]:
        """
        Check các triggers theo priority.
        Return trigger đầu tiên match (không fire >1 empathy/check).
        """
        checks = [
            (self._check_large_transaction, 1),
            (self._check_payday_splurge, 2),
            (self._check_over_budget_monthly, 3),
            (self._check_user_silent_7_days, 4),
            (self._check_user_silent_30_days, 5),
            (self._check_weekend_high_spending, 6),
            (self._check_first_saving_month, 7),
            (self._check_consecutive_over_budget, 8),
        ]
        
        for check_fn, priority in checks:
            trigger = await check_fn(user)
            if trigger:
                # Check cooldown
                if not await self._is_on_cooldown(user.id, trigger.name, trigger.cooldown_days):
                    return trigger
        
        return None
    
    async def _check_large_transaction(self, user) -> Optional[EmpathyTrigger]:
        """Giao dịch > 3x median 30 ngày gần đây."""
        async with get_session() as session:
            # Query latest transaction
            # Query median 30 days
            # ... (implementation details)
            
            latest = await self._get_latest_transaction(session, user.id)
            if not latest:
                return None
            
            # Bỏ qua nếu là chuyển khoản nội bộ
            if latest.category_code == "transfer":
                return None
            
            median = await self._get_median_transaction(session, user.id, days=30)
            
            if latest.amount > 3 * median and latest.amount > 500_000:  # Ít nhất 500k
                return EmpathyTrigger(
                    name="large_transaction",
                    priority=1,
                    cooldown_days=1,
                    context={
                        "amount": f"{int(latest.amount):,}đ",
                    },
                )
        return None
    
    async def _check_user_silent_7_days(self, user) -> Optional[EmpathyTrigger]:
        """User không tương tác 7 ngày."""
        async with get_session() as session:
            last_event = await self._get_last_event(session, user.id)
            if not last_event:
                return None
            
            days_silent = (datetime.utcnow() - last_event.timestamp).days
            
            if 7 <= days_silent < 30:
                return EmpathyTrigger(
                    name="user_silent_7_days",
                    priority=4,
                    cooldown_days=14,
                )
        return None
    
    async def _check_user_silent_30_days(self, user) -> Optional[EmpathyTrigger]:
        """User không tương tác 30 ngày."""
        async with get_session() as session:
            last_event = await self._get_last_event(session, user.id)
            if not last_event:
                return None
            
            days_silent = (datetime.utcnow() - last_event.timestamp).days
            
            if days_silent >= 30:
                return EmpathyTrigger(
                    name="user_silent_30_days",
                    priority=5,
                    cooldown_days=60,
                )
        return None
    
    async def _check_over_budget_monthly(self, user) -> Optional[EmpathyTrigger]:
        """Vượt ngân sách tháng ít nhất 10%."""
        # Implementation
        pass
    
    async def _check_payday_splurge(self, user) -> Optional[EmpathyTrigger]:
        """3 ngày sau lương chi > 35%."""
        # Implementation
        pass
    
    async def _check_weekend_high_spending(self, user) -> Optional[EmpathyTrigger]:
        """Cuối tuần chi > 50% chi tuần."""
        pass
    
    async def _check_first_saving_month(self, user) -> Optional[EmpathyTrigger]:
        """Tháng đầu tiên thu > chi."""
        pass
    
    async def _check_consecutive_over_budget(self, user) -> Optional[EmpathyTrigger]:
        """Vượt ngân sách 3 tháng liên tục trong cùng category."""
        pass
    
    async def _is_on_cooldown(self, user_id: int, trigger_name: str, days: int) -> bool:
        """Check xem trigger này đã fire gần đây chưa."""
        async with get_session() as session:
            # Query UserEvent type=empathy_fired, trigger_name=X
            # Nếu có trong vòng `days` ngày → on cooldown
            cutoff = datetime.utcnow() - timedelta(days=days)
            # ... query logic
            pass
    
    async def render_message(self, trigger: EmpathyTrigger, user) -> str:
        """Random pick message variation + render."""
        trigger_data = self._messages.get(trigger.name, {})
        templates = trigger_data.get("messages", [])
        
        if not templates:
            return ""
        
        template = random.choice(templates)
        
        # Render
        context = {
            "name": user.display_name or "bạn",
            **(trigger.context or {}),
        }
        
        try:
            return template.format(**context)
        except KeyError as e:
            print(f"Missing context key: {e}")
            return ""
    
    async def record_fired(self, user_id: int, trigger_name: str):
        """Lưu event để tính cooldown lần sau."""
        async with get_session() as session:
            event = UserEvent(
                user_id=user_id,
                event_type="empathy_fired",
                metadata={"trigger": trigger_name},
                timestamp=datetime.utcnow(),
            )
            session.add(event)
            await session.commit()
```

---

## 2.7 — UserEvent Model (Shared)

### File: `app/models/user_event.py`

Event log generic — dùng cho empathy cooldown, analytics, milestones...

```python
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Index
from app.database import Base


class UserEvent(Base):
    __tablename__ = "user_events"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    event_type = Column(String(50), nullable=False, index=True)
    metadata = Column(JSON, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    __table_args__ = (
        Index('idx_events_user_type_time', 'user_id', 'event_type', 'timestamp'),
    )
```

---

## 2.8 — Scheduled Job: Hourly Empathy Check

### File: `app/scheduled/check_empathy_triggers.py`

```python
"""
Chạy mỗi giờ (trừ 22h-7h để không spam đêm).
Check empathy triggers cho mọi user active.
"""

import asyncio
from datetime import datetime, time

from app.services.user_service import UserService
from app.bot.personality.empathy_engine import EmpathyEngine
from app.bot.bot_instance import bot


MAX_EMPATHY_PER_DAY = 2  # Mỗi user max 2 empathy messages/ngày


async def run_hourly_empathy_check():
    # Skip đêm
    now = datetime.now().time()
    if time(22, 0) <= now or now < time(7, 0):
        return
    
    user_service = UserService()
    engine = EmpathyEngine()
    
    active_users = await user_service.get_active_users(days=60)
    
    for user in active_users:
        try:
            # Check daily cap
            today_count = await _count_empathy_today(user.id)
            if today_count >= MAX_EMPATHY_PER_DAY:
                continue
            
            trigger = await engine.check_all_triggers(user)
            if not trigger:
                continue
            
            message = await engine.render_message(trigger, user)
            if not message:
                continue
            
            # Send
            await bot.send_message(chat_id=user.telegram_id, text=message)
            
            # Record (cho cooldown)
            await engine.record_fired(user.id, trigger.name)
            
            # Track
            from app.analytics import track, Event
            await track(Event(
                user_id=user.id,
                event_type="empathy_sent",
                properties={"trigger": trigger.name},
                timestamp=datetime.utcnow(),
            ))
            
            await asyncio.sleep(2)  # Rate limit
        except Exception as e:
            print(f"Empathy check error for user {user.id}: {e}")


async def _count_empathy_today(user_id: int) -> int:
    # Query UserEvent type=empathy_fired today
    pass
```

---

## ✅ Checklist Cuối Tuần 2

- [ ] Migrations `create_user_milestones`, `create_user_events` applied
- [ ] File `content/milestone_messages.yaml` — ít nhất 15 milestone types, mỗi loại 2-3 variations
- [ ] File `content/empathy_messages.yaml` — 8 empathy triggers đầy đủ
- [ ] `MilestoneService` detect được 5 loại milestone cơ bản (days 7/30/100, savings 1M/10M)
- [ ] `EmpathyEngine` implement ít nhất 4/8 triggers (large_transaction, silent_7_days, silent_30_days, weekend_high_spending — các cái khác có thể stub)
- [ ] Scheduled job `check_milestones` chạy 8h sáng
- [ ] Scheduled job `check_empathy_triggers` chạy mỗi giờ (7h-22h)
- [ ] Daily cap 2 empathy/user/day hoạt động
- [ ] Cooldown per-trigger hoạt động
- [ ] Tự test: force trigger các milestones, xem tin nhắn render đẹp

---

# 🎁 TUẦN 3: Surprise & Delight + Polish

## 3.1 — Streak System

### File: `alembic/versions/xxx_create_streaks.py`

```python
def upgrade():
    op.create_table(
        'user_streaks',
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('current_streak', sa.Integer, default=0, nullable=False),
        sa.Column('longest_streak', sa.Integer, default=0, nullable=False),
        sa.Column('last_active_date', sa.Date, nullable=True),
    )
```

### File: `app/services/streak_service.py`

```python
from datetime import date, timedelta
from app.models.streak import UserStreak
from app.database import get_session


class StreakService:
    async def record_activity(self, user_id: int) -> dict:
        """
        Gọi mỗi khi user ghi giao dịch.
        Return: {"streak_continued": bool, "current": int, "is_milestone": bool}
        """
        async with get_session() as session:
            streak = await session.get(UserStreak, user_id)
            if not streak:
                streak = UserStreak(
                    user_id=user_id,
                    current_streak=1,
                    longest_streak=1,
                    last_active_date=date.today(),
                )
                session.add(streak)
                await session.commit()
                return {"streak_continued": True, "current": 1, "is_milestone": False}
            
            today = date.today()
            yesterday = today - timedelta(days=1)
            
            if streak.last_active_date == today:
                # Đã ghi hôm nay rồi, không tính lại
                return {"streak_continued": False, "current": streak.current_streak, "is_milestone": False}
            elif streak.last_active_date == yesterday:
                # Liên tục
                streak.current_streak += 1
                streak.longest_streak = max(streak.longest_streak, streak.current_streak)
            else:
                # Đứt streak
                streak.current_streak = 1
            
            streak.last_active_date = today
            await session.commit()
            
            is_milestone = streak.current_streak in {7, 30, 100, 365}
            
            return {
                "streak_continued": True,
                "current": streak.current_streak,
                "is_milestone": is_milestone,
            }
```

### Integration: `handlers/transaction.py`

```python
async def handle_new_transaction(update, context, parsed_data):
    # ... existing code ...
    
    # Record streak
    streak_service = StreakService()
    streak_result = await streak_service.record_activity(user.id)
    
    # Nếu hit milestone → trigger milestone celebration
    if streak_result["is_milestone"]:
        from app.services.milestone_service import MilestoneService
        milestone_service = MilestoneService()
        # Record streak milestone...
```

---

## 3.2 — Fun Facts Generator

### File: `content/fun_fact_templates.yaml`

```yaml
# Fun facts - calculated từ dữ liệu user hàng tuần

coffee_equivalent:
  condition: "Chi cho cafe > 500k trong tháng"
  template: "☕ {name} biết không, tháng này bạn tiêu {amount} cho cafe — bằng khoảng {coffee_count} ly Highlands. Nếu pha ở nhà, có thể tiết kiệm ~{saving} đó 😄"

grab_count:
  condition: "Có ít nhất 5 lần Grab/tháng"
  template: "🚗 Tháng này bạn đi Grab {count} lần, tổng {amount}. Trung bình {avg}/chuyến. Nếu bạn sống gần MRT/bus có thể tiết kiệm đáng kể đấy!"

food_delivery_count:
  condition: "GrabFood/ShopeeFood > 10 lần/tháng"
  template: "🍱 {count} lần gọi đồ ăn tháng này! Tổng {amount}. Mình không phán xét — tiện lợi cũng đáng giá — nhưng tự nấu 1-2 bữa/tuần có thể tiết kiệm ~{saving}"

weekend_vs_weekday:
  condition: "Chi cuối tuần cao > 1.5x ngày thường"
  template: "📅 Fun fact: {name} chi cuối tuần trung bình {weekend_avg}/ngày, nhiều hơn {ratio}x so với ngày thường ({weekday_avg}/ngày). Weekend warrior! 🎉"

biggest_category:
  condition: "Always"
  template: "📊 Tuần này {name} chi nhiều nhất cho {category} ({amount}) — chiếm {percentage}% tổng chi. {category_insight}"

day_of_month_pattern:
  condition: "Rõ pattern chi tiêu theo ngày"
  template: "🔍 Mình để ý bạn thường chi nhiều nhất vào {day} đầu tháng ({amount}), ít nhất vào {day_low}. Pattern thú vị đó!"

new_merchant:
  condition: "Ghi merchant mới lần đầu"
  template: "🆕 Merchant mới: {merchant}! Đây là lần đầu {name} ghi chỗ này. Có đáng giá không nhỉ? 😄"

saving_projection:
  condition: "Có tiết kiệm đều"
  template: "💡 Với tốc độ tiết kiệm hiện tại ({monthly_saving}/tháng), sau 1 năm bạn sẽ có ~{year_projection}. Sau 5 năm có thể là ~{five_year_projection} (nếu để gửi lãi suất 6%/năm)"
```

### File: `app/bot/personality/fun_facts.py`

```python
"""
Fun facts generator - tạo insight từ dữ liệu user hàng tuần.
"""

import yaml
import random
from pathlib import Path
from app.services.report_service import ReportService


class FunFactGenerator:
    def __init__(self):
        self._templates = self._load_templates()
    
    def _load_templates(self) -> dict:
        path = Path(__file__).parent.parent.parent.parent / "content" / "fun_fact_templates.yaml"
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    async def generate_for_user(self, user) -> str | None:
        """
        Tính các facts applicable, chọn random 1 cái interesting nhất.
        """
        service = ReportService()
        facts = []
        
        # Coffee check
        coffee_spend = await service.get_category_spend(user.id, "food", days=30, merchant_contains="cafe")
        if coffee_spend > 500_000:
            facts.append(self._coffee_fact(user, coffee_spend))
        
        # Grab check
        grab_count, grab_total = await service.get_merchant_stats(user.id, "grab", days=30)
        if grab_count >= 5:
            facts.append(self._grab_fact(user, grab_count, grab_total))
        
        # Food delivery
        delivery_count, delivery_total = await service.get_food_delivery_stats(user.id, days=30)
        if delivery_count >= 10:
            facts.append(self._delivery_fact(user, delivery_count, delivery_total))
        
        # Weekend vs weekday
        weekend_avg, weekday_avg = await service.get_weekend_weekday_avg(user.id, days=30)
        if weekday_avg > 0 and weekend_avg / weekday_avg > 1.5:
            facts.append(self._weekend_fact(user, weekend_avg, weekday_avg))
        
        if not facts:
            # Fallback: biggest category
            biggest = await service.get_biggest_category(user.id, days=7)
            if biggest:
                facts.append(self._biggest_category_fact(user, biggest))
        
        return random.choice(facts) if facts else None
    
    def _coffee_fact(self, user, spend):
        template = self._templates["coffee_equivalent"]["template"]
        coffee_count = int(spend / 55_000)  # Avg 55k/ly
        saving = int(spend * 0.7)  # 70% saving nếu tự pha
        return template.format(
            name=user.display_name or "bạn",
            amount=f"{int(spend):,}đ",
            coffee_count=coffee_count,
            saving=f"{saving:,}đ",
        )
    
    # ... similar methods for other fact types
```

### File: `app/scheduled/weekly_fun_facts.py`

```python
"""Chủ nhật 19h gửi fun fact cho mỗi active user."""

async def run_weekly_fun_facts():
    user_service = UserService()
    generator = FunFactGenerator()
    
    active_users = await user_service.get_active_users(days=14)
    
    for user in active_users:
        fact = await generator.generate_for_user(user)
        if fact:
            await bot.send_message(chat_id=user.telegram_id, text=fact)
            await asyncio.sleep(1)
```

---

## 3.3 — Seasonal Content (Vietnam Calendar)

### File: `content/seasonal_calendar.yaml`

```yaml
# Vietnam-specific seasonal events
# Dates dùng lunar/solar calendar tùy event

events:
  - name: tet_preparation
    trigger_date: "2026-02-10"  # 10 ngày trước Tết
    message: "🧧 Còn ~10 ngày nữa là Tết rồi {name}!\n\nMình biết đây là thời điểm chi tiêu tăng cao. Muốn mình tạo riêng category 'Tết 2026' để theo dõi không? Bao gồm: lì xì, sắm Tết, biếu xén...\n\nSau Tết bạn sẽ thấy rất rõ đã chi vào đâu 🌸"
    action: "offer_tet_category"
  
  - name: tet_day
    trigger_date: "2026-02-17"  # Mùng 1 Tết
    message: "🎊 Chúc {name} một năm mới an khang thịnh vượng!\n\nTiền bạc năm nay dư dả, kế hoạch tài chính thuận lợi 💰\n\nMình vẫn sẽ ở đây đồng hành cùng bạn cả năm nhé 💚"
  
  - name: post_tet_review
    trigger_date: "2026-02-25"  # 1 tuần sau Tết
    message: "🧮 Tết đã qua rồi {name}. Muốn xem tổng kết chi Tết của mình không?\n\nMình đã ghi lại: {tet_total}, bao gồm... [breakdown]\n\nKhông phán xét — Tết mà! Chỉ để biết, năm sau plan tốt hơn 🌱"
  
  - name: mid_autumn
    trigger_date: "2026-09-25"  # Trung thu
    message: "🥮 Trung thu đến rồi!\n\n{name} có nhớ năm ngoái bạn chi {last_year_mid_autumn} cho bánh trung thu không? (Không nhớ thì bình thường 😄). Năm nay có dự định gì không?"
  
  - name: back_to_school
    trigger_date: "2026-08-15"
    message: "📚 Mùa tựu trường sắp đến {name}!\n\nNếu bạn có con, đây thường là thời điểm chi tiêu tăng: sách vở, đồng phục, học phí. Mình có thể giúp bạn plan ngân sách riêng cho mùa này không?"
  
  - name: black_friday
    trigger_date: "2025-11-25"  # 4 ngày trước BF
    message: "🛍️ Black Friday sắp đến {name}.\n\nMình không nói đừng mua — mình chỉ muốn hỏi: bạn có muốn đặt sẵn ngân sách 'Shopping dịp lễ' để tiêu có ý thức hơn không?\n\nVí dụ: 2tr cho đợt này. Vượt thì mình cảnh báo 😊"
  
  - name: double_11
    trigger_date: "2026-11-10"
    message: "11.11 tới rồi {name}!\n\nMình để ý năm ngoái bạn chi {last_year_double_11} vào dịp này. Năm nay muốn đặt limit sớm không? 🛒"
  
  - name: year_end_review
    trigger_date: "2026-12-28"
    message: "📅 Còn 3 ngày nữa hết năm {name} ơi!\n\nMình đang chuẩn bị báo cáo năm đặc biệt cho bạn — kiểu Wrapped ấy 🎁 Sẽ gửi bạn vào 31/12 nhé, đảm bảo nhiều insight thú vị!"
```

### File: `app/scheduled/seasonal_notifier.py`

```python
"""
Chạy 8h sáng mỗi ngày.
Check seasonal calendar, gửi tin nhắn nếu hôm nay match.
"""

import yaml
from datetime import date
from pathlib import Path


async def run_seasonal_check():
    path = Path("content/seasonal_calendar.yaml")
    with open(path, encoding="utf-8") as f:
        calendar = yaml.safe_load(f)
    
    today = date.today().isoformat()
    
    for event in calendar["events"]:
        if event["trigger_date"] == today:
            await _fire_seasonal_event(event)


async def _fire_seasonal_event(event):
    user_service = UserService()
    active_users = await user_service.get_active_users(days=30)
    
    for user in active_users:
        # Fetch context cho render (ví dụ: last_year_mid_autumn)
        context = await _fetch_event_context(user, event["name"])
        
        message = event["message"].format(
            name=user.display_name or "bạn",
            **context,
        )
        
        await bot.send_message(chat_id=user.telegram_id, text=message)
        await asyncio.sleep(1)
```

**Lưu ý Tết:** Tết thay đổi hàng năm theo âm lịch. Cần update YAML hàng năm, HOẶC dùng thư viện `lunardate` để tính tự động:

```python
from lunardate import LunarDate

# Tết = mùng 1 tháng 1 âm lịch
lunar_new_year = LunarDate(2026, 1, 1).toSolarDate()
```

---

## 3.4 — Memory-Aware Goal Reminders

### File: `app/bot/personality/memory_moments.py`

Nhắc lại goal user đã chọn ở onboarding, 1 tuần 1 lần:

```python
"""
Goal reminder - nhắc user về mục tiêu họ đã chọn.
Chạy mỗi thứ 2 sáng.
"""

GOAL_REMINDER_TEMPLATES = {
    "save_more": [
        "💰 Chào tuần mới {name}!\n\nNhớ bạn nói muốn 'tiết kiệm nhiều hơn' không? Tuần trước bạn đã {saving_progress} — {encouragement}",
    ],
    "understand": [
        "📊 Sáng thứ 2 vui {name}!\n\nBạn muốn 'hiểu mình tiêu vào đâu' — và mình thấy tuần qua top category của bạn là {top_cat} với {top_amount}. Insight nhỏ 💡",
    ],
    "reach_goal": [
        "🎯 Tuần mới mới lại {name}!\n\nMục tiêu bạn đang theo đuổi cần thêm {remaining} để hoàn thành. Tuần này cùng nhau tiến thêm một chút nhé 💪",
    ],
    "less_stress": [
        "🧘 Chào buổi sáng {name}.\n\nThư thả nhé — bạn nói muốn 'bớt stress về tiền' và mình thấy bạn đang đi đúng hướng. Tuần này {positive_signal} 🌸",
    ],
}


async def send_weekly_goal_reminder(user):
    if not user.primary_goal:
        return
    
    templates = GOAL_REMINDER_TEMPLATES.get(user.primary_goal, [])
    if not templates:
        return
    
    template = random.choice(templates)
    
    # Fetch context tùy goal
    context = await _fetch_goal_context(user)
    
    message = template.format(
        name=user.display_name or "bạn",
        **context,
    )
    
    await bot.send_message(chat_id=user.telegram_id, text=message)
```

---

## 3.5 — Bộ Sticker Telegram (Optional nhưng nên làm)

### Công việc:

- [ ] **Thiết kế/thuê 10-15 stickers** dựa trên mascot đã chọn ở Phase 1
- [ ] **Expression cần có**:
  - Vui mừng (khi user đạt milestone)
  - Ngạc nhiên (khi user chi lớn)
  - Lo lắng nhẹ (khi vượt ngân sách)
  - Ngủ (nhắc user ngủ sớm khi chi tiêu đêm)
  - Chúc mừng Tết
  - Thumb up
  - Vỗ tay
  - Ôm (empathy)
  - Câm nín (khi user chi cực lớn)
  - Heart eyes (khi user tiết kiệm giỏi)

- [ ] **Upload lên Telegram** qua @Stickers bot
- [ ] **Lưu sticker IDs** trong `config/stickers.py`:
  ```python
  STICKERS = {
      "celebrate": "CAACAgI...",
      "worried": "CAACAgI...",
      # ...
  }
  ```

- [ ] **Dùng stickers trong các moment quan trọng**:
  ```python
  from config.stickers import STICKERS
  
  # Sau milestone message
  await bot.send_sticker(chat_id=user.telegram_id, sticker=STICKERS["celebrate"])
  ```

---

## 3.6 — Polish & Beta Testing

### Content Quality Review

- [ ] **Đọc lại toàn bộ YAML content** — tự test đọc thành tiếng xem có ấm áp không
- [ ] **Invite native VN speakers review** — 2-3 người, focus vào tone
- [ ] **Catch awkward phrasing** — tin nhắn dịch từ English thường hơi "cứng"

### Friends Beta Round 2

- [ ] **Invite 10-15 friends** (đã có từ Phase 1, thêm 5-10 người mới)
- [ ] **Specific feedback questions**:
  1. Khi bot chúc mừng milestone, bạn cảm thấy thế nào? (Vui / Bình thường / Giả tạo)
  2. Có lúc nào bot nhắn mà bạn thấy "đúng ghê, nó hiểu mình" không? Khi nào?
  3. Có lúc nào tin nhắn của bot làm bạn khó chịu không? Tại sao?
  4. Giọng điệu bot: Quá formal / Vừa / Quá thân mật?
  5. Tần suất tin nhắn: Ít quá / Vừa / Nhiều quá?

### Metrics to Check

- [ ] **Onboarding completion rate**: target >70%
- [ ] **Onboarding time**: median <5 phút
- [ ] **Empathy message response rate**: bao nhiêu % user respond sau khi nhận empathy?
- [ ] **Streak retention**: % user có streak >7 ngày
- [ ] **Negative feedback rate**: bao nhiêu % user complain về tin nhắn

---

## ✅ Checklist Cuối Tuần 3

- [ ] Streak system hoạt động (record_activity + milestones)
- [ ] Fun fact generator — ít nhất 5 fact types
- [ ] Weekly fun fact job chạy CN 19h
- [ ] Seasonal calendar có ít nhất 8 events VN
- [ ] Seasonal notifier chạy 8h sáng, support lunar dates
- [ ] Goal reminder job chạy thứ 2 sáng
- [ ] Sticker pack upload (optional)
- [ ] Content review pass với native speakers
- [ ] Beta testing round 2 với 10+ users
- [ ] Metrics dashboard show onboarding/empathy/streak numbers

---

# 📊 Metrics Phase 2

Ngoài metrics Phase 1 đã có, Phase 2 track thêm:

**Onboarding Funnel:**
- `onboarding_started` → `step_1` → ... → `onboarding_completed`
- Drop-off rate mỗi step

**Memory & Empathy:**
- `milestone_celebrated` — theo type
- `empathy_sent` — theo trigger
- `empathy_response_rate` — % user reply sau empathy message

**Retention Signals:**
- D7 retention sau onboarding (target: >50%)
- D30 retention (target: >30%)
- Weekly active users (target: tăng 10% mỗi tuần đầu)

**Content Quality:**
- Sticker usage (có dùng không?)
- Fun fact open rate
- Seasonal event response rate

---

# 🎯 Exit Criteria Của Phase 2

Chỉ chuyển Phase 3 khi TẤT CẢ đạt:

- [ ] Onboarding flow hoàn chỉnh, completion rate >70% qua 10+ users
- [ ] Ít nhất 15 milestone types implement, test fire được
- [ ] Ít nhất 6 empathy triggers hoạt động
- [ ] Streak system hoạt động, ít nhất 3 user đạt streak >7
- [ ] Fun facts gửi weekly, có 5+ fact types
- [ ] Seasonal calendar có ít nhất 8 events plan cho 12 tháng tới
- [ ] Beta users cho feedback: ít nhất 60% nói tin nhắn bot "dễ thương" / "ấm áp"
- [ ] Không có user nào complain bot spam
- [ ] D7 retention của users mới cải thiện rõ so với trước Phase 2

**Nếu retention không cải thiện** → dừng lại, điều tra tại sao. Phase 2 là về retention — nếu không lên được, đừng vội sang Phase 3.

---

# 🚧 Bẫy Thường Gặp (Tránh!)

## 1. Over-engineering Empathy Rules

Dễ rơi vào bẫy viết 50+ rules nhưng 90% không fire đúng context. Bắt đầu với **6-8 rules thật chất lượng**, mỗi rule test kỹ trước khi thêm rule mới.

## 2. Content Quá Cheesy

Giữa "ấm áp" và "sến súa" là ranh giới mong manh. Test bằng cách đọc to — nếu bạn thấy xấu hổ khi đọc, user cũng sẽ thấy vậy.

❌ Tránh: "Ôi {name} ơi, mình nhớ bạn quá nhiều!" 
✅ Tốt: "Lâu rồi không gặp {name}. Mọi thứ ổn chứ?"

## 3. Spam Empathy Messages

Empathy đúng lúc = quý giá. Empathy sai lúc/quá nhiều = khó chịu. **Daily cap 2 empathy/user** là nguyên tắc không nên phá.

## 4. Seasonal Events Bị Lệch Date

Tết, Trung thu dùng âm lịch → đừng hardcode date. Dùng `lunardate` hoặc update YAML hàng năm.

## 5. Onboarding Quá Dài

3 phút là target. Nếu user cần 5+ phút → rút gọn. Questions không essential cho Phase 2 (ví dụ: thu nhập, giới tính) → để Phase 4.

## 6. Không A/B Test Tone

Người VN có tone preferences khác nhau. Gen Z thích emoji nhiều; người 35+ thích formal hơn. Nên có 2-3 tone variants và track response rate.

## 7. Quên Migration Rollback

Nhiều migrations mới trong Phase này. Nếu bug production → phải rollback được. Luôn implement `downgrade()` cẩn thận.

## 8. YAML Syntax Errors

YAML sensitive với indentation. 1 dấu cách sai = cả file fail parse. Setup linting pre-commit: `yamllint content/*.yaml`

---

# 📚 Tài Liệu Tham Khảo

- Behavioral economics cơ bản: "Nudge" (Thaler & Sunstein)
- UX Writing cho bot: https://material.io/design/communication/writing.html
- Telegram Sticker bot: @Stickers
- Vietnamese lunar date: https://pypi.org/project/lunardate/
- APScheduler docs: https://apscheduler.readthedocs.io/

---

# 🎉 Next Step

Khi Phase 2 "Done", cân nhắc **beta soft launch** cho 30-50 users thật (không phải friends) để test personality ở scale. Đây là lúc lý tưởng vì:
- Bot đã có vỏ đẹp (Phase 1)
- Bot có hồn (Phase 2)
- Nhưng chưa có Phase 3 (capture) — nên users sẽ phàn nàn về nhập liệu → xác nhận rằng đây là pain point lớn nhất → motivate bạn làm Phase 3 tốt hơn.

Sau đó tạo file `phase-3-detailed.md` với nội dung:
- SMS regex parsers cho top 5 bank VN
- Smart categorizer (rule-based + LLM fallback)
- SMS Forwarder setup guide (video + text)
- Screenshot OCR với Claude Vision
- Voice input với Whisper
- Daily wrap-up flow

**Nguyên tắc vàng lặp lại: Personality trước, feature sau. Phase 2 là đầu tư cho retention — đừng vội bỏ qua vì thấy "ít code" 💚**

**Good luck với Phase 2! 💝**
