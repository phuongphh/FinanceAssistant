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
- [ ] Accessible from bot menu button — add `/about` → "Thông tin ứng dụng" vào `setup_commands.py`
- [ ] Response time <1 second

### Message Content

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

**Data & Security Statement:**
```
🔒 Bảo mật dữ liệu
Dữ liệu tài chính của bạn được mã hóa và lưu trữ an toàn.
Chúng tôi không bao giờ chia sẻ thông tin cá nhân với bên thứ ba.
```

**Copyright:**
```
© 2026 Nui Truc AI. All rights reserved.
```

### Inline Keyboard Buttons (1 per row)
- [ ] **[🌐 Website Công Ty]** → `https://nuitruc.ai`
- [ ] **[🔏 Chính Sách Bảo Mật]** → `https://nuitruc.ai/privacy`
- [ ] **[📧 Hỗ Trợ]** → `mailto:admin@nuitruc.ai`

> ℹ️ Trang `https://nuitruc.ai/privacy` đang được chuẩn bị — deploy song song với feature này.

---

## Technical Implementation

### File
- [ ] `app/bot/handlers/about_handler.py` với `cmd_about` function

### Version Management
- [ ] Version string định nghĩa tại `app/config.py` hoặc `app/version.py`: `APP_VERSION = "1.3.8.01"`
- [ ] Không hardcode inline trong handler — dễ update sau này

### Registration
- [ ] `CommandHandler("about", cmd_about)` trong bot router
- [ ] Added vào `BOT_COMMANDS` trong `app/bot/setup_commands.py`:
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

`[🌐 Website Công Ty]`
`[🔏 Chính Sách Bảo Mật]`
`[📧 Hỗ Trợ]`

---

## Definition of Done

- [ ] `/about` command works end-to-end
- [ ] All 3 inline buttons open correct URLs
- [ ] Version string sourced from central config (`APP_VERSION`)
- [ ] Copyright year: **2026**
- [ ] Command appears in Telegram bot menu button
- [ ] Tested on mobile (iPhone + Android) — links open correctly
- [ ] `https://nuitruc.ai/privacy` live khi ship

---

## Notes
- **Estimate:** ~0.5 day
- **Priority:** Medium — ship trước public beta
