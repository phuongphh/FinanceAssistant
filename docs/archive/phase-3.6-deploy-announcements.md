# Phase 3.6 — Deploy Announcement Templates

> **Story:** [P3.6-S11 / #171](../issues/active/issue-171.md)
> **Status:** Reference copy — operator broadcasts these manually.

The two messages below are sent to all active users via the existing
notification path (``services/telegram_service.send_message`` against
each user's ``chat_id``). Edits don't require a deploy — content team
can iterate on tone here, operator copy-pastes when broadcasting.

When all users have received both messages and the 1-month legacy
redirect window expires, this file can be archived.

---

## Pre-deploy (1 day before cutover)

```
📢 *Bé Tiền sắp được nâng cấp giao diện mới!*

Menu sẽ rõ ràng hơn với 5 mảng:
💎 Tài sản • 💸 Chi tiêu • 💰 Dòng tiền • 🎯 Mục tiêu • 📊 Thị trường

Cập nhật vào ngày mai 7h sáng. Mọi tính năng vẫn còn —
chỉ tổ chức gọn hơn thôi!
```

## Post-deploy (within 1 hour of cutover)

```
✨ *Menu mới đã sẵn sàng!*

Gõ /menu để khám phá. Hoặc cứ hỏi mình tự nhiên
như cũ — mình hiểu mà 😊
```

---

## Broadcast snippet

For one-off broadcasts, the operator can paste this into a Python
shell on the host:

```python
from backend.database import get_session_factory
from backend.services.telegram_service import send_message
from sqlalchemy import select
from backend.models.user import User

MESSAGE = """..."""  # paste either template above

async def broadcast():
    factory = get_session_factory()
    async with factory() as db:
        rows = (await db.execute(
            select(User.telegram_id).where(User.is_active == True)
        )).all()
    for (tg_id,) in rows:
        await send_message(tg_id, MESSAGE, parse_mode="Markdown")
```

Throttle by sleeping between sends if user count grows beyond ~30 —
Telegram allows up to ~30 msgs/sec to different chats.
