# Phase 3.8.5 — Pre-Launch Readiness (Chi Tiết Triển Khai)

> **Đây là phase nhỏ, inserted giữa Phase 3.8 và Phase 3.9, để chuẩn bị soft launch tháng 6/2026.**
>
> **Thời gian ước tính:** 3-4 ngày (với Claude Code velocity)  
> **Mục tiêu cuối Phase:** User có thể gửi feedback + xem/edit profile của mình. Backend tự động classify feedback, profile auto-derive từ existing data.  
> **Điều kiện "Done":** `/feedback` command working, profile menu working, active prompts scheduled, admin có thể view feedback database.
>
> **Prerequisites:** Phase 3.8 (wealth completion) đã ship. Profile cần data từ Phase 3A (assets), Phase 3.8 (income, goals) để compute auto-derived stats.

---

## 🎯 Triết Lý Thiết Kế Phase 3.8.5

5 nguyên lý quan trọng:

### 1. "Zero Friction Feedback"
User submit feedback chỉ với 2 actions: command `/feedback` + type/voice. **Không** chọn category (backend tự classify), **không** chọn priority (backend tự assess), **không** điền form.

→ Mục tiêu: maximize feedback volume. Càng dễ, càng nhiều insight.

### 2. "Anti-Form Profile"
Profile là **VIEW-MODE primary**, không phải data entry form. Hệ thống đã biết mọi thứ cần biết (assets, transactions, behavior). Profile chỉ surface những thông tin đó cho user thấy.

→ Editable fields cực ít: chỉ 3 (display name, age range optional, notification time).

### 3. "Backend Smart, Frontend Dumb"
Feedback classification, sentiment analysis, priority — **tất cả ở backend**, leverage DeepSeek (cheap LLM). User không cần biết.

### 4. "Strict Active Prompts"
Active feedback prompts max 4-6 lần/năm. Trigger sau **major events** thật sự (post-onboarding day 7, sau briefing 30 days, post-major-feature, post-milestone-reached). Never weekly check-ins.

### 5. "Wealth Level VN-Native"
Tier name dùng tiếng Việt natively: **Khởi Đầu / Trẻ Năng Động / Trung Lưu Vững / Tinh Hoa**. Don't expose English internal names tới user.

---

## 📅 Phân Bổ Thời Gian (3-4 ngày)

| Ngày | Component | Deliverable |
|------|-----------|-------------|
| **Ngày 1** | Feedback System backend + command | `/feedback` working, DB storage |
| **Ngày 2** | Feedback auto-classification + Active prompts | DeepSeek classifier, scheduler |
| **Ngày 3** | Profile View + auto-derived stats | Menu Profile, view-mode primary |
| **Ngày 4** | Profile edit + integration tests | Edit flows, admin feedback view |

---

## 🗂️ Cấu Trúc Thư Mục Mở Rộng

```
finance_assistant/
├── app/
│   ├── feedback/                        # ⭐ NEW MODULE
│   │   ├── models/
│   │   │   └── feedback.py              # Feedback model
│   │   ├── services/
│   │   │   ├── feedback_service.py      # CRUD + storage
│   │   │   ├── classifier.py            # Auto-classify via DeepSeek
│   │   │   └── prompt_scheduler.py      # Active prompts logic
│   │   └── handlers/
│   │       ├── feedback_command.py      # /feedback
│   │       └── prompt_handlers.py       # Inline buttons after prompts
│   │
│   ├── profile/                         # ⭐ NEW MODULE
│   │   ├── models/
│   │   │   └── user_profile.py          # UserProfile model
│   │   ├── services/
│   │   │   ├── profile_service.py       # Profile CRUD
│   │   │   ├── stats_aggregator.py      # Auto-derived stats
│   │   │   └── wealth_level_mapper.py   # VN tier mapping
│   │   └── handlers/
│   │       └── profile_menu.py          # Menu integration
│   │
│   └── agent/                           # Existing
│       └── tools/
│           └── (no new tools — Phase 3.8.5 is UX layer, no agent integration needed)
│
├── content/
│   ├── feedback_prompts.yaml            # ⭐ NEW - active prompt templates
│   └── wealth_levels.yaml               # ⭐ NEW - VN tier mapping
│
└── tests/
    └── test_phase_3_8_5/
        ├── test_feedback.py
        ├── test_profile.py
        └── test_active_prompts.py
```

**Note:** Phase 3.8.5 KHÔNG cần thêm agent tools (no `get_feedback`, no `update_profile` via NLP). Đây là phase UX layer thuần — user interact qua commands + menu, không qua natural language. Giữ scope tight.

---

# 🔧 NGÀY 1-2: Feedback System

## 1.1 — Data Model

### File: `app/feedback/models/feedback.py`

```python
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from datetime import datetime

class Feedback(Base):
    __tablename__ = "feedbacks"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Raw content
    content = Column(Text, nullable=False)  # User's free-form text
    
    # Auto-classified by backend
    category = Column(String(50), nullable=True)
    # Categories: bug | suggestion | praise | question | complaint | other
    
    sentiment = Column(String(20), nullable=True)
    # Sentiment: positive | neutral | negative
    
    priority = Column(String(20), nullable=True)
    # Priority: low | medium | high
    
    classification_confidence = Column(Float, nullable=True)  # 0-1
    classifier_version = Column(String(50), nullable=True)  # for tracking
    
    # Trigger context
    trigger = Column(String(50), nullable=False)
    # Triggers: passive_command | onboarding_day_7 | post_briefing_30d | post_milestone | post_feature_launch
    
    # Context snapshot (for analysis)
    context = Column(JSON, nullable=True)
    # Example context:
    # {
    #   "user_wealth_level": "Trung Lưu Vững",
    #   "account_age_days": 47,
    #   "recent_actions": ["briefing_read", "expense_added"],
    #   "current_phase_version": "3.8",
    #   "active_features": ["rental_tracking", "goals", "recurring"]
    # }
    
    # Admin tracking
    status = Column(String(20), default="new")
    # Statuses: new | reviewing | actioned | dismissed
    admin_notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
```

**Why store full context?** Khi analyze feedback sau này, biết user state lúc submit cực valuable. "User report bug trong Twin lúc account age 5 ngày" → onboarding issue, không phải Twin issue.

---

## 1.2 — Feedback Command Handler

### File: `app/feedback/handlers/feedback_command.py`

```python
async def handle_feedback_command(update, context):
    """Handle /feedback command — entry point."""
    user_id = update.effective_user.id
    
    # Set conversation state to awaiting feedback content
    await set_user_state(user_id, "awaiting_feedback_text")
    
    await update.message.reply_text(
        "💌 Cảm ơn bạn muốn góp ý! Mình rất biết ơn 💚\n\n"
        "Bạn cứ chia sẻ thoải mái — bug, gợi ý, lời khen, câu hỏi, "
        "hoặc bất cứ điều gì bạn nghĩ. Gõ message tiếp theo nhé.",
        reply_markup=ReplyKeyboardRemove()
    )

async def handle_feedback_text(update, context):
    """Handle next message after /feedback — submit feedback."""
    user_id = update.effective_user.id
    text = update.message.text
    
    if not text or len(text.strip()) < 5:
        await update.message.reply_text(
            "Mình chưa nhận được nội dung rõ. Gõ lại nhé hoặc /cancel để hủy."
        )
        return
    
    # Capture context snapshot
    context_snapshot = await ContextSnapshotService().capture(user_id)
    
    # Save feedback (with classification deferred to background)
    feedback = await FeedbackService().create(
        user_id=user_id,
        content=text,
        trigger="passive_command",
        context=context_snapshot,
    )
    
    # Trigger background classification job
    await classifier_queue.enqueue(feedback.id)
    
    # Clear conversation state
    await clear_user_state(user_id)
    
    # Acknowledge to user
    await update.message.reply_text(
        "✅ Đã ghi nhận! Cảm ơn bạn rất nhiều 💚\n\n"
        "Team Bé Tiền sẽ review trong vòng 7 ngày. "
        "Mọi feedback đều giúp sản phẩm tốt hơn cho cộng đồng."
    )
```

**Critical UX decisions:**
- KHÔNG show category buttons — user just types
- Acknowledgment immediate (don't wait for classification)
- "7 ngày review" sets expectation realistic
- Mention "cộng đồng" để user feel part of something

### Edge Cases

```python
# Empty/too short feedback
if len(text.strip()) < 5:
    return "Mình chưa nhận được nội dung rõ..."

# Too long (spam protection)
if len(text) > 5000:
    return "Feedback dài quá! Gõ ngắn gọn hơn nhé (tối đa 5000 ký tự)."

# Rate limit (max 5 feedbacks/day per user)
if await get_today_feedback_count(user_id) >= 5:
    return "Bạn đã gửi 5 feedback hôm nay rồi. Để tránh spam, mình giới hạn 5/ngày."

# /cancel during awaiting state
if text == "/cancel":
    await clear_user_state(user_id)
    return "OK, đã hủy. Quay lại bất cứ lúc nào với /feedback."
```

---

## 1.3 — Backend Auto-Classification

### File: `app/feedback/services/classifier.py`

```python
class FeedbackClassifier:
    """Auto-classify feedback using DeepSeek (cheap LLM)."""
    
    PROMPT_TEMPLATE = """
Classify this user feedback for a Vietnamese personal finance app called "Bé Tiền".

User feedback: "{content}"

Classify into these dimensions:

1. CATEGORY (choose one):
   - bug: User reports something not working
   - suggestion: User suggests a feature or improvement
   - praise: User expresses positive feeling
   - question: User asks how to do something
   - complaint: User unhappy but not bug-specific
   - other: Doesn't fit above

2. SENTIMENT:
   - positive | neutral | negative

3. PRIORITY:
   - high: Critical bug, blocks user, security issue
   - medium: Notable issue or valuable suggestion
   - low: Minor, nice-to-have, simple question

Respond ONLY in JSON format:
{{
  "category": "...",
  "sentiment": "...",
  "priority": "...",
  "confidence": 0.0-1.0,
  "reasoning": "1 sentence why"
}}
"""
    
    async def classify(self, feedback_content: str) -> dict:
        response = await deepseek_client.complete(
            prompt=self.PROMPT_TEMPLATE.format(content=feedback_content),
            max_tokens=200,
            temperature=0.1,  # Low temp for consistency
        )
        
        try:
            result = json.loads(response.strip())
            return {
                "category": result.get("category", "other"),
                "sentiment": result.get("sentiment", "neutral"),
                "priority": result.get("priority", "low"),
                "confidence": float(result.get("confidence", 0.5)),
                "classifier_version": "deepseek-v1-2026-05",
            }
        except (json.JSONDecodeError, ValueError) as e:
            # Fallback: classify as "other" with low confidence
            logger.warning(f"Classification failed: {e}")
            return {
                "category": "other",
                "sentiment": "neutral",
                "priority": "low",
                "confidence": 0.0,
                "classifier_version": "fallback",
            }
```

### Background Job Worker

```python
async def process_feedback_classification_queue():
    """Worker processes pending classifications."""
    while True:
        feedback_id = await classifier_queue.dequeue(timeout=30)
        if not feedback_id:
            continue
        
        feedback = await FeedbackService().get_by_id(feedback_id)
        if not feedback or feedback.category:
            continue  # Already classified
        
        try:
            classification = await FeedbackClassifier().classify(feedback.content)
            
            await FeedbackService().update_classification(
                feedback_id=feedback.id,
                category=classification["category"],
                sentiment=classification["sentiment"],
                priority=classification["priority"],
                confidence=classification["confidence"],
                classifier_version=classification["classifier_version"],
            )
        except Exception as e:
            logger.error(f"Classification failed for feedback {feedback_id}: {e}")
            # Will retry next cycle
```

**Cost analysis:**
- DeepSeek: ~$0.0001 per classification
- Even 1000 feedbacks/month = ~$0.10
- Negligible cost

---

## 1.4 — Active Prompts Scheduler

### File: `content/feedback_prompts.yaml`

```yaml
prompts:
  - id: "post_onboarding_day_7"
    trigger: "account_age_days == 7"
    message: |
      💚 Bạn đã đồng hành với Bé Tiền 1 tuần rồi!
      
      Bạn cảm thấy thế nào? Có gì mình có thể cải thiện không?
      Chia sẻ cảm nhận đầu tiên nhé 🙏
    cta_button: "Chia sẻ cảm nhận"
    skip_button: "Để sau"
    cooldown_days: 60  # Don't re-prompt same trigger for 60 days
  
  - id: "post_briefing_30_reads"
    trigger: "briefing_read_count == 30"
    message: |
      📊 Bạn đã đọc 30 daily briefings — wow!
      
      Briefing có giúp bạn quản lý tài chính tốt hơn không?
      Bạn muốn mình thay đổi gì để briefing hữu ích hơn?
    cta_button: "Góp ý về briefing"
    skip_button: "Để sau"
    cooldown_days: 90
  
  - id: "post_first_goal_completed"
    trigger: "goals_completed_count == 1"
    message: |
      🎉 Chúc mừng bạn đạt mục tiêu đầu tiên!
      
      Bé Tiền đã giúp gì cho hành trình này? 
      Mình muốn nghe câu chuyện của bạn 💚
    cta_button: "Kể chuyện"
    skip_button: "Để sau"
    cooldown_days: 180
  
  - id: "post_phase_4_launch"
    trigger: "feature_used == 'twin_first_view'"
    message: |
      ✨ Bạn vừa xem Financial Twin đầu tiên!
      
      Tính năng này có giúp bạn nhìn về tương lai tài chính rõ hơn không?
      Feedback thật giúp mình nhiều lắm 🙏
    cta_button: "Góp ý về Twin"
    skip_button: "Để sau"
    cooldown_days: 30
  
  - id: "post_3_months_active"
    trigger: "account_age_days == 90"
    message: |
      🌟 3 tháng đồng hành — cảm ơn bạn!
      
      Nhìn lại hành trình, Bé Tiền có làm bạn hài lòng không?
      Có điều gì bạn muốn thay đổi không?
    cta_button: "Đánh giá tổng thể"
    skip_button: "Để sau"
    cooldown_days: 180
```

### Prompt Scheduler

```python
class PromptScheduler:
    """Trigger active feedback prompts based on user events."""
    
    async def check_and_send_prompts(self, user_id: int):
        """Called after key user events (briefing read, goal completed, etc.)"""
        
        # Get user state
        user_stats = await UserStatsService().get(user_id)
        
        # Load all prompt configs
        prompts = await self._load_prompts()
        
        for prompt in prompts:
            # Check if trigger condition met
            if not self._evaluate_trigger(prompt.trigger, user_stats):
                continue
            
            # Check cooldown — don't re-send within cooldown_days
            last_sent = await self._get_last_prompt_sent(user_id, prompt.id)
            if last_sent and (date.today() - last_sent).days < prompt.cooldown_days:
                continue
            
            # Check rate limit — max 2 active prompts per month
            recent_prompts = await self._count_prompts_last_30_days(user_id)
            if recent_prompts >= 2:
                continue
            
            # Send prompt
            await self._send_prompt(user_id, prompt)
            return  # One prompt per check
    
    async def _send_prompt(self, user_id, prompt):
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(prompt.cta_button, callback_data=f"prompt:reply:{prompt.id}"),
                InlineKeyboardButton(prompt.skip_button, callback_data=f"prompt:skip:{prompt.id}"),
            ]
        ])
        
        await telegram_bot.send_message(
            chat_id=user_chat_id,
            text=prompt.message,
            reply_markup=keyboard,
        )
        
        await self._log_prompt_sent(user_id, prompt.id)
```

### When to call check_and_send_prompts

Hook into these events:
- After morning briefing read → check `post_briefing_30_reads`
- After goal marked completed → check `post_first_goal_completed`
- After Twin first view → check `post_phase_4_launch`
- Daily cron → check `post_onboarding_day_7`, `post_3_months_active`

**Important:** Max 2 active prompts/month/user enforcement is hard limit, regardless of triggers.

---

# 🎨 NGÀY 3-4: User Profile

## 2.1 — Data Model

### File: `app/profile/models/user_profile.py`

```python
class UserProfile(Base):
    __tablename__ = "user_profiles"
    
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    
    # Editable fields (user provides)
    display_name = Column(String(100), nullable=True)  # override Telegram first_name
    age_range = Column(String(20), nullable=True)  # "20-29", "30-39", "40-49", "50+", null
    
    # Notification preferences
    briefing_enabled = Column(Boolean, default=True)
    briefing_time = Column(String(10), default="07:00")  # HH:MM
    reminder_enabled = Column(Boolean, default=True)
    reminder_time = Column(String(10), default="09:00")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
```

**Note:** Auto-derived stats KHÔNG store ở đây — compute on-demand từ existing tables (assets, transactions, goals). Avoid stale data.

---

## 2.2 — Wealth Level Mapper

### File: `content/wealth_levels.yaml`

```yaml
levels:
  - id: "khoi_dau"
    name_vn: "Khởi Đầu"
    name_en: "Starter"
    icon: "🌱"
    net_worth_min: 0
    net_worth_max: 30000000  # 30tr
    description: "Bắt đầu hành trình quản lý tài sản"
    
  - id: "tre_nang_dong"
    name_vn: "Trẻ Năng Động"
    name_en: "Young Professional"
    icon: "🚀"
    net_worth_min: 30000000
    net_worth_max: 200000000  # 200tr
    description: "Đang xây dựng tài sản, năng động"
    
  - id: "trung_luu_vung"
    name_vn: "Trung Lưu Vững"
    name_en: "Mass Affluent"
    icon: "💎"
    net_worth_min: 200000000
    net_worth_max: 1000000000  # 1 tỷ
    description: "Tài sản ổn định, đa dạng hóa"
    
  - id: "tinh_hoa"
    name_vn: "Tinh Hoa"
    name_en: "High Net Worth"
    icon: "🏆"
    net_worth_min: 1000000000  # 1 tỷ+
    net_worth_max: null
    description: "Tài sản đáng kể, cần quản lý chuyên sâu"
```

### File: `app/profile/services/wealth_level_mapper.py`

```python
class WealthLevelMapper:
    """Map net worth → Vietnamese tier name."""
    
    def __init__(self):
        self.levels = self._load_levels()
    
    def get_level(self, net_worth: Decimal) -> dict:
        """Return level dict with name_vn, icon, description."""
        for level in self.levels:
            min_w = level["net_worth_min"]
            max_w = level["net_worth_max"]
            
            if net_worth < min_w:
                continue
            if max_w is None or net_worth < max_w:
                return level
        
        # Fallback (shouldn't happen)
        return self.levels[0]
    
    def get_next_level(self, current_net_worth: Decimal) -> dict:
        """Return next tier user is working toward."""
        for level in self.levels:
            if current_net_worth < level["net_worth_min"]:
                return level
        return None  # Already at top tier
    
    def get_progress_to_next(self, current_net_worth: Decimal) -> dict:
        """Calculate % progress to next tier."""
        current_level = self.get_level(current_net_worth)
        next_level = self.get_next_level(current_net_worth)
        
        if not next_level:
            return {"at_top": True, "progress_pct": 100}
        
        # Progress within current level
        range_size = next_level["net_worth_min"] - current_level["net_worth_min"]
        progress = current_net_worth - current_level["net_worth_min"]
        pct = float(progress / range_size * 100) if range_size > 0 else 0
        
        return {
            "at_top": False,
            "progress_pct": min(100, max(0, pct)),
            "amount_to_next": next_level["net_worth_min"] - current_net_worth,
            "next_level_name": next_level["name_vn"],
        }
```

---

## 2.3 — Stats Aggregator

### File: `app/profile/services/stats_aggregator.py`

```python
class ProfileStatsAggregator:
    """Compute auto-derived stats for profile view."""
    
    async def aggregate(self, user_id: int) -> dict:
        """Return comprehensive profile stats."""
        
        # Account age
        user = await UserService().get_by_id(user_id)
        account_age_days = (date.today() - user.created_at.date()).days
        
        # Wealth level
        net_worth = await WealthService().get_total_net_worth(user_id)
        level_info = WealthLevelMapper().get_level(net_worth)
        progress = WealthLevelMapper().get_progress_to_next(net_worth)
        
        # Asset diversity
        asset_types_count = await AssetService().count_distinct_types(user_id)
        # Returns count of: cash, stocks, real_estate, crypto, gold, savings (max 6)
        
        # Tracking activity
        transaction_count_total = await TransactionService().count_all(user_id)
        transaction_count_this_month = await TransactionService().count_this_month(user_id)
        
        # Goals
        goals_active = await GoalService().count_active(user_id)
        goals_completed = await GoalService().count_completed(user_id)
        
        # Briefings read
        briefing_read_count = await BriefingService().count_reads(user_id)
        
        # Streak (consecutive days với activity)
        current_streak = await self._compute_streak(user_id)
        
        # Net worth change since start
        first_net_worth = await WealthService().get_first_recorded_net_worth(user_id)
        if first_net_worth and first_net_worth > 0:
            net_worth_change_pct = float((net_worth - first_net_worth) / first_net_worth * 100)
        else:
            net_worth_change_pct = None
        
        return {
            "account_age_days": account_age_days,
            "wealth_level": level_info,  # name_vn, icon, description
            "wealth_progress": progress,  # progress to next level
            "asset_types_count": asset_types_count,
            "transaction_count_total": transaction_count_total,
            "transaction_count_this_month": transaction_count_this_month,
            "goals_active": goals_active,
            "goals_completed": goals_completed,
            "briefing_read_count": briefing_read_count,
            "current_streak": current_streak,
            "net_worth_change_pct": net_worth_change_pct,
        }
```

---

## 2.4 — Profile Menu Handler

### File: `app/profile/handlers/profile_menu.py`

```python
async def handle_profile_view(update, context):
    """Render profile view from /menu → 👤 Profile."""
    user_id = update.effective_user.id
    
    # Get profile + stats
    profile = await ProfileService().get_or_create(user_id)
    stats = await ProfileStatsAggregator().aggregate(user_id)
    
    # Resolve display name
    display_name = profile.display_name or update.effective_user.first_name
    
    # Build message
    message = format_profile_message(display_name, stats)
    
    # Build keyboard
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Đổi tên hiển thị", callback_data="profile:edit:name")],
        [InlineKeyboardButton("🎂 Đổi nhóm tuổi", callback_data="profile:edit:age")],
        [InlineKeyboardButton("🔔 Cài thông báo", callback_data="profile:edit:notifications")],
        [InlineKeyboardButton("🔙 Quay lại Menu", callback_data="menu:main")],
    ])
    
    await update.callback_query.edit_message_text(message, reply_markup=keyboard, parse_mode="Markdown")

def format_profile_message(display_name: str, stats: dict) -> str:
    level = stats["wealth_level"]
    progress = stats["wealth_progress"]
    
    msg = f"👤 **{display_name}** {level['icon']} {level['name_vn']}\n"
    msg += f"_{level['description']}_\n\n"
    
    msg += f"💚 Đồng hành cùng Bé Tiền **{stats['account_age_days']} ngày**\n\n"
    
    # Wealth journey
    if not progress["at_top"]:
        amount_to_next = format_vnd_short(progress["amount_to_next"])
        msg += f"📈 **Hành trình tài sản:**\n"
        msg += f"• Tiến độ tới {progress['next_level_name']}: {progress['progress_pct']:.0f}%\n"
        msg += f"• Còn cần: {amount_to_next}\n"
        if stats["net_worth_change_pct"] is not None:
            sign = "+" if stats["net_worth_change_pct"] >= 0 else ""
            msg += f"• Net worth thay đổi từ khi bắt đầu: {sign}{stats['net_worth_change_pct']:.1f}%\n"
    else:
        msg += f"🏆 Bạn đã đạt level cao nhất!\n"
    msg += "\n"
    
    # Tracking activity
    msg += f"📊 **Hoạt động:**\n"
    msg += f"• {stats['asset_types_count']} loại tài sản đang theo dõi\n"
    msg += f"• {stats['transaction_count_this_month']} giao dịch tháng này\n"
    msg += f"• {stats['goals_active']} mục tiêu đang theo đuổi"
    if stats["goals_completed"] > 0:
        msg += f" • {stats['goals_completed']} đã hoàn thành ✅"
    msg += "\n\n"
    
    # Streak + briefing
    msg += f"🔥 **Streak hiện tại:** {stats['current_streak']} ngày liên tiếp\n"
    msg += f"📅 **Daily briefing:** đã đọc {stats['briefing_read_count']} lần\n"
    
    return msg
```

### Edit Flows

```python
async def handle_edit_name(update, context):
    """Edit display name flow."""
    user_id = update.effective_user.id
    await set_user_state(user_id, "awaiting_display_name")
    
    await update.callback_query.edit_message_text(
        "📝 Tên hiển thị mới của bạn? (Tối đa 50 ký tự)\n\n"
        "Hoặc /cancel để giữ nguyên."
    )

async def handle_display_name_input(update, context):
    user_id = update.effective_user.id
    new_name = update.message.text.strip()
    
    if new_name == "/cancel":
        await clear_user_state(user_id)
        return await show_profile_view(user_id)
    
    if len(new_name) > 50:
        return await update.message.reply_text("Tên dài quá! Tối đa 50 ký tự nhé.")
    
    if len(new_name) < 1:
        return await update.message.reply_text("Tên không được trống.")
    
    await ProfileService().update(user_id, display_name=new_name)
    await clear_user_state(user_id)
    
    await update.message.reply_text(f"✅ Đã đổi tên hiển thị thành: **{new_name}**")
    await show_profile_view(user_id)

async def handle_edit_age(update, context):
    """Show age range buttons."""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("20-29", callback_data="profile:set_age:20-29"),
            InlineKeyboardButton("30-39", callback_data="profile:set_age:30-39"),
        ],
        [
            InlineKeyboardButton("40-49", callback_data="profile:set_age:40-49"),
            InlineKeyboardButton("50+", callback_data="profile:set_age:50+"),
        ],
        [InlineKeyboardButton("🚫 Không muốn nói", callback_data="profile:set_age:none")],
    ])
    
    await update.callback_query.edit_message_text(
        "🎂 Bạn thuộc nhóm tuổi nào?\n\n"
        "_Thông tin này giúp Bé Tiền cá nhân hóa lời khuyên cho bạn._",
        reply_markup=keyboard,
    )

async def handle_edit_notifications(update, context):
    """Show notification settings."""
    profile = await ProfileService().get_or_create(update.effective_user.id)
    
    briefing_status = "✅ Bật" if profile.briefing_enabled else "🔕 Tắt"
    reminder_status = "✅ Bật" if profile.reminder_enabled else "🔕 Tắt"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📅 Daily Briefing: {briefing_status}", callback_data="profile:toggle:briefing")],
        [InlineKeyboardButton(f"⏰ Briefing time: {profile.briefing_time}", callback_data="profile:set:briefing_time")],
        [InlineKeyboardButton(f"⏰ Reminder: {reminder_status}", callback_data="profile:toggle:reminder")],
        [InlineKeyboardButton(f"⏰ Reminder time: {profile.reminder_time}", callback_data="profile:set:reminder_time")],
        [InlineKeyboardButton("🔙 Quay lại", callback_data="profile:view")],
    ])
    
    await update.callback_query.edit_message_text(
        "🔔 **Cài đặt thông báo**\n\nNhấn để bật/tắt hoặc đổi giờ:",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
```

---

## 2.5 — Menu Integration

### File: `app/menu/handlers.py` (extend Phase 3.6 menu)

Add new menu item:

```python
MAIN_MENU_BUTTONS = [
    # ... existing buttons ...
    [InlineKeyboardButton("👤 Profile của tôi", callback_data="menu:profile")],
    # ... existing buttons ...
]

async def handle_menu_callback(update, context):
    callback_data = update.callback_query.data
    
    if callback_data == "menu:profile":
        return await handle_profile_view(update, context)
    # ... existing handlers ...
```

---

## ✅ Checklist Cuối Phase 3.8.5

### Component A: Feedback
- [ ] Migration creates `feedbacks` table
- [ ] `/feedback` command working — captures free-form text
- [ ] Acknowledgment immediate after submission
- [ ] Edge cases handled (empty, too long, /cancel, rate limit)
- [ ] DeepSeek classifier worker running
- [ ] Classification updates feedback record async
- [ ] 5 active prompts loaded from YAML
- [ ] Prompt scheduler hooked into events (briefing read, goal completed, etc.)
- [ ] Cooldown enforcement (don't spam)
- [ ] Max 2 prompts/month rate limit
- [ ] Admin can query feedbacks (basic — DB query for now)

### Component B: Profile
- [ ] Migration creates `user_profiles` table
- [ ] Wealth levels YAML loaded với Vietnamese mapping
- [ ] WealthLevelMapper computes level + progress correctly
- [ ] ProfileStatsAggregator returns all auto-derived stats
- [ ] Profile menu item added to Phase 3.6 main menu
- [ ] Profile view renders correctly (name, level, stats, streaks)
- [ ] Edit display name flow working
- [ ] Edit age range flow working
- [ ] Notification settings flow working (toggle + time change)
- [ ] /cancel returns to profile view gracefully

---

# 🎯 Exit Criteria Phase 3.8.5

Phase 3.8.5 ready to ship khi:

- [ ] User có thể gửi feedback bằng `/feedback` command
- [ ] Backend tự động classify feedback (≥80% accuracy on test set)
- [ ] Active prompts trigger đúng (test 1 trigger end-to-end)
- [ ] User có thể xem profile với đầy đủ auto-derived stats
- [ ] Wealth level hiển thị tiếng Việt (Khởi Đầu / Trẻ Năng Động / etc.)
- [ ] Edit flows working (name, age, notifications)
- [ ] No regressions trong Phase 3.8 features
- [ ] Test suite passes
- [ ] Admin có thể query feedback database (simple)

---

# 🚧 Bẫy Thường Gặp Phase 3.8.5

## 1. Active Prompts Spam
**Symptom:** User receives 5 prompts in 1 week.  
**Cause:** Cooldown logic broken hoặc rate limit not enforced.  
**Action:** Always check cooldown_days + max 2/month before sending.

## 2. Classification Errors Don't Block Storage
**Symptom:** Feedback save fails because LLM API down.  
**Cause:** Classification synchronous in submit flow.  
**Action:** Save feedback FIRST, classify async via queue.

## 3. Profile Stats Stale
**Symptom:** User added 5tr to savings, profile still shows old net worth.  
**Cause:** Caching wealth level/stats.  
**Action:** Compute on-demand. Don't cache. Phase 3.8.5 reads từ source tables.

## 4. Wealth Level Boundary Issues
**Symptom:** Net worth = 30,000,000đ exactly. Which level?  
**Cause:** Boundary logic ambiguous.  
**Action:** Use `>= min AND < max` consistently. 30tr → Trẻ Năng Động (next tier).

## 5. Display Name Special Characters
**Symptom:** User enters emoji/Unicode → DB error.  
**Cause:** Column too narrow or encoding issue.  
**Action:** UTF-8 mb4, allow up to 50 chars, sanitize control chars.

## 6. Active Prompt Trigger Race Condition
**Symptom:** User reads briefing 30 times → 2 prompts triggered same time.  
**Cause:** No locking when checking trigger.  
**Action:** Use database lock or idempotency key on prompt_sent_log.

---

# 📊 Metrics Phase 3.8.5

Track from Day 1:

**Feedback metrics:**
- Total feedbacks/week (target: ≥10 from active users)
- Active prompt response rate (target: ≥30%)
- Classification confidence (target: ≥80% confidence ≥0.7)
- Categorization breakdown (suggestion / bug / praise / other ratio)

**Profile metrics:**
- Profile view rate (target: ≥40% users open profile within first week)
- Edit interaction rate (target: ≥20% edit at least 1 field)
- Wealth level distribution (will inform marketing)

**Quality:**
- Feedback rate-limit hits (target: <5% users hit 5/day)
- Classification override rate (admin manually re-classify) (target: <10%)

---

**Phase 3.8.5 = pre-launch foundation. Sau phase này, Bé Tiền ready cho soft launch tháng 6 với full feedback loop + user identity. 💚🚀**
