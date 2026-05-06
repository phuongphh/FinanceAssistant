# Issue #233

[Feature] Add /about command — Product About page with version, privacy policy & company info

## User Story

As a user of Bé Tiền (FinanceAssistant), I want to type `/about` and see a clean, trustworthy About page so that I know who built this product, what version I'm using, and how my financial data is handled.

---

## Background & Motivation

Finance apps handle sensitive personal data. A well-crafted About page:
- Builds **trust** (company identity, privacy statement)
- Signals **professionalism** (versioning, copyright)
- Provides **support path** (contact email)
- Satisfies **transparency expectations** for fintech products

---

## Acceptance Criteria

### Command
- [ ] `/about` command registered and handled
- [ ] Accessible from bot menu button (Phase 3.6 command list — add `/about` → "Thông tin ứng dụng")
- [ ] Response time <1 second

### Message Content

Message must include all of the following sections:

**Header:**
```
💎 Bé Tiền — Personal CFO
Trợ lý CFO cá nhân đầu tiên dành cho người Việt
```

**Version & Build:**
```
📦 Phiên bản: 1.3.8.01
```

**Company:**
```
🏢 Phát triển bởi: Nui Truc AI
```

**Data & Security Statement (short, trust-building):**
```
🔒 Bảo mật dữ liệu
Dữ liệu tài chính của bạn được mã hóa và lưu trữ an toàn.
Chúng tôi không bao giờ chia sẻ thông tin cá nhân với bên thứ ba.
```

**Copyright:**
```
© [YEAR] Nui Truc AI. All rights reserved.
```
> ⚠️ **Cần xác nhận:** Copyright year là **2006** hay **2026**? Nếu 2006 là năm thành lập công ty thì format có thể là "© 2006–2026". Vui lòng confirm trước khi ship.

### Inline Keyboard Buttons (3 buttons, 1 per row)
- [ ] **[🌐 Website Công Ty]** → opens `https://nuitruc.ai`
- [ ] **[🔏 Chính Sách Bảo Mật]** → opens `https://nuitruc.ai/privacy`
- [ ] **[📧 Hỗ Trợ]** → opens `mailto:admin@nuitruc.ai` (or Telegram deep link if preferred)

---

## Prerequisite (Blocker)

> ⚠️ **Privacy Policy page phải tồn tại trước khi ship feature này.**

- [ ] **Tạo trang** `https://nuitruc.ai/privacy` với nội dung Privacy Policy đầy đủ
- [ ] Trang phải bao gồm: data collected, how it's used, retention policy, user rights, contact info
- [ ] **Không ship `/about` cho đến khi URL này live** — broken privacy link là red flag với users

---

## Technical Implementation

### File
- [ ] `app/bot/handlers/about_handler.py` với `cmd_about` function

### Logic
```python
async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = build_about_message()
    keyboard = build_about_keyboard()
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
```

### Version Management
- [ ] Version string `1.3.8.01` extracted từ central config (không hardcode inline)
- [ ] Define trong `app/config.py` hoặc `app/version.py`: `APP_VERSION = "1.3.8.01"`
- [ ] Cho phép update version mà không cần sửa handler

### Registration
- [ ] Registered trong bot router: `CommandHandler("about", cmd_about)`
- [ ] Added vào `BOT_COMMANDS` list trong `app/bot/setup_commands.py`:
  `("/about", "Thông tin ứng dụng")`

---

## Sample Output

```
💎 *Bé Tiền — Personal CFO*
_Trợ lý CFO cá nhân đầu tiên dành cho người Việt_

📦 *Phiên bản:* 1.3.8.01
🏢 *Phát triển bởi:* Nui Truc AI

━━━━━━━━━━━━━━━
🔒 *Bảo mật dữ liệu*
Dữ liệu tài chính của bạn được mã hóa và lưu trữ an toàn.
Chúng tôi không bao giờ chia sẻ thông tin cá nhân với bên thứ ba.
━━━━━━━━━━━━━━━

© 2026 Nui Truc AI. All rights reserved.
```

Buttons:
`[🌐 Website Công Ty]  [🔏 Chính Sách Bảo Mật]  [📧 Hỗ Trợ]`

---

## Definition of Done

- [ ] `/about` command works end-to-end
- [ ] All 3 inline buttons open correct URLs
- [ ] Privacy Policy page is live at `https://nuitruc.ai/privacy`
- [ ] Copyright year confirmed and correct
- [ ] Version string sourced from central config
- [ ] Command appears in Telegram bot menu button
- [ ] Tested on mobile (iPhone + Android) — links open correctly

---

## Notes

- **Estimate:** ~0.5 day (code) + variable (Privacy Policy page creation)
- **Priority:** Medium — should ship before public beta
- **Dependency:** Privacy Policy page at `https://nuitruc.ai/privacy`
