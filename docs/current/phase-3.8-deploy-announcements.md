# Phase 3.8 — Deploy Announcement Templates

> **Phase:** 3.8 — Wealth Completion (rental, multi-income, recurring +
> reminders, cashflow forecast, goals templates).
> **Reference:** [phase-3.8-detailed.md](./phase-3.8/phase-3.8-detailed.md)
> **Status:** Reference copy — operator broadcasts via
> `scripts/broadcast_announcement.py` (see § Broadcast tool below).

Phase 3.8 is bigger than 3.6 — it ships **5 distinct capabilities**, not
a UI revamp. So this file holds a **3-message campaign** instead of a
single pre/post pair: one teaser, one launch announcement, one
follow-up nudge a week later when reminders start firing.

Edits don't require a deploy — content team can iterate on tone here,
operator runs the broadcast script when ready. When the 2-week
follow-up window closes, this file can be archived.

Tone follows [tone_guide.md](./tone_guide.md): "mình" / "bạn", warm,
no judgement, give choices not commands.

---

## Message 1 — Pre-deploy teaser (1 day before cutover)

**ID:** `teaser`
**When:** ~24h before deploy, evening (~19h-21h) for highest open rate.
**Goal:** Build anticipation, prep users that something useful is coming.

```
✨ *Bé Tiền có vài tính năng mới sắp lên!*

Ngày mai mình sẽ giúp bạn:

🏠 Theo dõi BĐS cho thuê (tiền thuê, chi phí, lợi suất)
💼 Ghi nhiều nguồn thu nhập (lương, freelance, cổ tức, lãi…)
⏰ Nhắc các khoản chi định kỳ (thuê nhà, điện nước, subscription)
📈 Dự đoán dòng tiền 3 tháng tới
🎯 Đặt mục tiêu từ 7 mẫu sẵn (mua xe, mua nhà, hưu trí…)

Mọi thứ cũ vẫn nguyên — chỉ đầy đủ hơn thôi.

Hẹn gặp bạn sáng mai 💚
```

---

## Message 2 — Launch announcement (within 1h of cutover)

**ID:** `launch`
**When:** Right after deploy passes smoke test.
**Goal:** Tell users it's live, give 1 concrete next-step per persona
band so nobody stares at a "what now?" screen.

```
🎉 *5 tính năng mới đã sẵn sàng!*

Bạn có thể thử ngay:

🏠 *Có BĐS cho thuê?*
Vào /menu → Tài sản → chọn BĐS → "Đánh dấu cho thuê"

💼 *Thu nhập từ nhiều nguồn?*
/menu → Dòng tiền → "Thêm nguồn thu nhập"

⏰ *Có khoản chi hàng tháng cố định?*
/menu → Chi tiêu → "Khoản định kỳ"
Mình sẽ nhắc trước 2 ngày tới hạn.

📈 *Muốn xem trước dòng tiền?*
Cứ hỏi mình: _"tháng tới tiết kiệm được bao nhiêu?"_

🎯 *Có mục tiêu trong đầu?*
/menu → Mục tiêu → chọn mẫu (mua xe, mua nhà…)
Mình tính giúp bạn cần để dành bao nhiêu mỗi tháng.

Cứ hỏi tự nhiên như cũ nhé — mình hiểu mà 😊
```

---

## Message 3 — Follow-up nudge (7 days after launch)

**ID:** `followup`
**When:** +7 days. Skip users who already added rental / income /
recurring / goal — they don't need the nudge.
**Goal:** Re-activate users who saw the launch but didn't try.

```
👋 *Tuần qua thế nào rồi?*

Mình thấy bạn chưa thử mấy tính năng mới — không sao,
chỉ nhắc nhẹ vì bạn có thể bỏ lỡ vài thứ tiện:

⏰ Đặt 1 khoản định kỳ (vd: thuê nhà, internet)
→ Mình nhắc trước hạn, đỡ quên.

🎯 Đặt 1 mục tiêu (vd: du lịch, mua xe)
→ Biết cần để dành bao nhiêu/tháng để đạt được.

Hỏi mình _"giúp tôi đặt mục tiêu"_ hoặc _"thêm khoản định kỳ"_
là bắt đầu được rồi 💚
```

---

## Broadcast tool

**Script:** `scripts/broadcast_announcement.py`

One-click broadcast. The operator picks which message to send by ID,
the script reads it from this file, lists eligible recipients, asks for
confirmation, then sends with throttling.

### Usage

```bash
# Preview without sending
python scripts/broadcast_announcement.py --message teaser --dry-run

# Send teaser to all active users
python scripts/broadcast_announcement.py --message teaser

# Send launch announcement
python scripts/broadcast_announcement.py --message launch

# Send follow-up only to users who haven't engaged with new features
python scripts/broadcast_announcement.py --message followup --skip-engaged

# Send to a single test user (your own telegram_id)
python scripts/broadcast_announcement.py --message launch --only 123456789
```

### What it does

1. Parses this markdown file → finds the message block by `--message <id>`.
2. Queries `users` table for active recipients
   (`is_active = TRUE`, optional filters).
3. Prints recipient count + first/last names + first 200 chars of the
   message, asks `Send to N users? [y/N]`.
4. Sends via `services/telegram_service.send_message` with Markdown
   parse mode, sleeping 50ms between sends (well under Telegram's
   30 msg/sec global limit).
5. Logs each send result; prints summary `sent / failed / skipped`.
6. On failure (e.g. user blocked the bot), continues — failures are
   logged but never abort the run.

### Options

| Flag | Purpose |
|---|---|
| `--message <id>` | Required. One of `teaser`, `launch`, `followup`. |
| `--dry-run` | Render + list recipients, don't send. |
| `--only <telegram_id>` | Send to one user (testing). |
| `--skip-engaged` | For `followup`: skip users with rental / income stream / recurring pattern / active goal added since launch. |
| `--throttle-ms <n>` | Per-message sleep (default 50). Bump to 200+ if user count > 1k. |
| `--file <path>` | Source markdown (default this file). Useful for testing variants. |

### Safety

- Refuses to run without `OWNER_TELEGRAM_ID` set in env (so a wrong
  config never broadcasts to nobody / wrong DB).
- Confirmation prompt is mandatory unless `--yes` passed.
- Each send is wrapped in try/except; failures logged with `telegram_id`
  for follow-up.
- Dry-run is the default safe mode for content review — use it before
  every real send to catch Markdown rendering issues.

---

## Editing checklist

Before running broadcast for any message:

- [ ] Read the message out loud — if it sounds stiff, rewrite.
- [ ] Verify Markdown renders (asterisks balanced, no stray underscores).
- [ ] Cross-check feature names match what's actually shipped.
- [ ] Test with `--only <your_telegram_id>` first.
- [ ] Then `--dry-run` against full audience to confirm count.
- [ ] Then real send.
