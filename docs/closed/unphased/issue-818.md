# Issue #818

[db] Migration 20260523_life_insurance_date_fields_backfill fails — wrong down_revision + revision ID too long


## Nguyên nhân

Migration mới `20260523_life_insurance_date_fields_backfill.py` không thể apply do 2 lỗi:

### 1. Down revision không phải head hiện tại
`down_revision = "20260522_fix_transactions_amount_numeric"` 
Nhưng head hiện tại là merge revision `02940674e911` (vì `20260522_fix_transactions_amount_numeric` đã là 1 trong 2 parents của merge revision này).

Lỗi alembic:
```
KeyError: '20260522_fix_transactions_amount_numeric'
UserWarning: Revision 20260522_fix_transactions_amount_numeric referenced from ... is not present
```

### 2. Revision ID quá dài (42 ký tự) > varchar(32)
`revision = "20260523_life_insurance_date_fields_backfill"` — 42 ký tự
Cột `alembic_version.version_num` là `varchar(32)` → truncation error.

Ngay cả sau khi fix down_revision thành `02940674e911`, migration chạy upgrade code thành công nhưng fail ở bước cuối:
```
StringDataRightTruncationError: value too long for type character varying(32)
UPDATE alembic_version SET version_num='20260523_life_insurance_date_fields_backfill' 
WHERE alembic_version.version_num = '02940674e911'
```

## Files liên quan
- `alembic/versions/20260523_life_insurance_date_fields_backfill.py`

## Fix cần làm
- Sửa `down_revision` từ `20260522_fix_transactions_amount_numeric` thành `02940674e911` (merge head hiện tại)
- Sửa `revision` thành ID ngắn hơn ≤ 32 ký tự (vd: `20260523_insurance_backfill`)
