# Issue #567

[Story] US5: Daily transaction summary (22:00 cron)

**Parent Epic:** #562 (Expense Enhancement)

Cron 22:00 moi ngay gui danh sach giao dich trong ngay.

## Acceptance Criteria
- [ ] Cron 22:00 ICT moi ngay
- [ ] Query transactions cua user trong ngay hom nay
- [ ] Format: "+100k tien momo tu ban P\n-50k an trua\n-200k mua sach..."
- [ ] Chi hien neu co giao dich -> khong spam
- [ ] Tong ket cuoi: "Hom nay: +Xđ vao, -Yđ ra" hoac "Khong co giao dich nao"
- [ ] Feature flag DAILY_TRANSACTION_SUMMARY_ENABLED

Close #562
