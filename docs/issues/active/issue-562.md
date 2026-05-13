# Issue #562

[Epic] Expense Enhancement — Money-In/Expense with Source Tracking, Daily Summary & Dashboard

## Epic: Expense Enhancement

**Priority:** High  
**Estimate:** ~4-5 ngay  
**Stories:** 6

## Mục tiêu
Mở rộng chức năng Chi tiêu hiện tại với 3 trục chính:
1. **Transaction types**: Phân biệt rõ **Expense** (chi tiêu, trừ nguồn) và **Money In** (tiền vào, cộng nguồn)
2. **Source tracking**: Mỗi transaction gắn với nguồn (tiền mặt, tài khoản thanh toán, ví điện tử)
3. **Daily summary**: Cron 22:00 gửi danh sách giao dịch trong ngày
4. **Dashboard**: Hiển thị Money In list song song với Expense, có CRUD

### Stories in this Epic
_(Se update)_
- [ ] [Story] US1: Transaction model — extend with source, type, linked asset
- [ ] [Story] US2: Expense flow — source selection + syntax (+/-)
- [ ] [Story] US3: Money In entry flow — income tracking with source
- [ ] [Story] US4: Menu Chi tiêu — help text & syntax guide
- [ ] [Story] US5: Daily transaction summary (22:00 cron)
- [ ] [Story] US6: Expense Dashboard — Money In list + CRUD

### Scope Notes
- Sources: Tien mat, Tai khoan thanh toan, Vi (Momo/VNPay/ZaloPay/ViettelPay)
- Syntax: "+200k tien thuong" = Money In, "-100k an trua" = Expense
- Money In examples: duoc thuong, duoc bo cho, duoc li xi
