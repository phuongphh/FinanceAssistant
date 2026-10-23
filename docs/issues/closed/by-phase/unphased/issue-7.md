# Issue #7

[Feature] /menu command - Display all available bot commands

## Overview
Implement a `/menu` command that displays all available bot features and allows users to trigger actions directly from the menu. This improves UX by giving users a clear overview of what the bot can do.

## Requirements

### /menu Command
When user types `/menu`, the bot responds with an interactive menu listing all available features with trigger buttons.

---

### 1. 📧 Gmail Invoice Scanner
- **Trigger:** Button "Quét Gmail tìm hoá đơn mới"
- **Description:** Scan Gmail from the last scan timestamp to now, looking for new invoices from:
  - **UOB Bank** — bank statements, transaction notifications
  - **Grab** — ride/food receipts
  - **Xanh SM** — ride receipts
  - **Traveloka** — booking/travel receipts
- **Behavior:** Returns list of new invoices found; updates last scan timestamp after each run

---

### 2. 📸 OCR Invoice
- **Trigger:** Button "Chụp/gửi hoá đơn để OCR"
- **Description:** User sends an image of a receipt/invoice → bot extracts data via OCR and saves to DB
- **Data extracted:** Merchant name, amount, date, category

---

### 3. ✍️ Manual Expense Entry
- **Trigger:** Button "Nhập chi tiêu thủ công"
- **Description:** User inputs expense details manually (amount, category, note, date) → bot saves to DB
- **Format:** Simple guided conversation flow to collect expense data

---

### 4. 📊 Send Report
- **Trigger:** Button "Xem báo cáo chi tiêu"
- **Description:** Generate and send spending report
- **Options:**
  - Report by day / week / month
  - Breakdown by category
  - Summary of total spending

---

### 5. 📈 Market Information
- **Trigger:** Button "Thông tin thị trường"
- **Description:** Fetch and display latest financial market data relevant to user, including:
  - Stock market indices (VN-Index, HNX, etc.)
  - Exchange rates (USD/VND, EUR/VND, etc.)
  - Gold prices
  - Crypto prices (if applicable)
- **Behavior:** Returns latest market snapshot with trends (up/down vs previous session)

---

### 6. 🎯 Financial Goals Management
- **Trigger:** Button "Quản lý mục tiêu tài chính"
- **Description:** Allow users to set, track, and manage personal financial goals
- **Features:**
  - Create new financial goal (e.g. "Tiết kiệm 100 triệu đến 31/12/2025")
  - View list of active goals with progress bar
  - Update goal progress manually or auto-sync from expense data
  - Mark goal as completed
  - Delete/edit existing goals

---

### 7. (Extensible)
Menu should be designed to easily add new features in the future.

---

## Menu UI Example
```
📋 *FinanceAssistant - Menu chính*

Chọn tính năng bạn muốn sử dụng:

[📧 Quét Gmail tìm hoá đơn]
[📸 OCR hoá đơn]
[✍️ Nhập chi tiêu thủ công]
[📊 Xem báo cáo chi tiêu]
[📈 Thông tin thị trường]
[🎯 Quản lý mục tiêu tài chính]
```

## Acceptance Criteria
- [ ] `/menu` command is registered and responds correctly
- [ ] All buttons are displayed and functional
- [ ] Gmail scanner scans from last scan timestamp to now
- [ ] Gmail scanner detects invoices from UOB, Grab, Xanh SM, Traveloka
- [ ] OCR feature accepts image and extracts expense data to DB
- [ ] Manual entry guides user through input flow and saves to DB
- [ ] Report feature generates spending summary
- [ ] Market information displays latest rates, indices, and prices
- [ ] Financial goals feature supports full CRUD operations
- [ ] Goal progress is trackable and visualized
- [ ] Menu is extensible for future features

## Implementation Notes
- Store `last_scan_timestamp` per user in DB for Gmail scanning
- Use Telegram inline keyboard buttons for the menu
- Gmail scanning should run asynchronously (notify user when done)
- OCR can use Google Vision API or Tesseract
- Market data can be fetched from public APIs (VNDirect, CafeF, CoinGecko, v.v.)
- Financial goals stored in DB with fields: goal_id, user_id, title, target_amount, current_amount, deadline, status
