# Issue #564

[Story] US2: Expense flow — add source selection with +/- syntax

**Parent Epic:** #562 (Expense Enhancement)

Khi user nhap expense, ho tro syntax "-100k an trua" + chon nguon tien.

## Acceptance Criteria
- [ ] Syntax "-100k an trua" -> tao expense transaction, parse so tien + merchant
- [ ] Bot hoi: "Tru tien tu nguon nao?" [Tien mat] [Tai khoan] [Vi dien tu]
- [ ] Neu chon Vi -> hoi: [Momo] [VNPay] [ZaloPay] [ViettelPay]
- [ ] Sau khi xac nhan: tru source + hien confirmation
- [ ] Syntax "100k an trua" (khong co +/-) -> default la expense, hoi confirm
- [ ] Validation: source phai co so du >= so tien (canh bao, khong block)
- [ ] Backward compatible: neu khong chon source -> ghi nhan khong lien ket

Close #562
