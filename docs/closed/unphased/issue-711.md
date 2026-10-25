# Issue #711

Delete asset: multiple matches with no asset_type shows wrong screen

# Issue #705 — Delete asset: multiple matches show type picker instead of asset list

## Nguyên nhân

Khi user gõ "xoá tài sản HPG", nếu có nhiều hơn 1 asset match (vd: 2 cổ phiếu HPG), handler `action_delete_asset` kiểm tra:

```python
if len(matches) > 1 and asset_type:
    await show_asset_delete_list(...)
    return ""
```

Nếu `asset_type` là None (NLU không extract được), code rơi xuống:

```python
if asset_type:
    ...
    return ""

await show_asset_delete_type_picker(...)  # ❌ show type picker thay vì danh sách
```

## Kỳ vọng

Nếu có nhiều matches nhưng thiếu `asset_type`, handler nên tự infer `asset_type` từ các matches (vì tất cả matches cùng type) rồi show danh sách các tài sản đó cho user chọn.

Hoặc đơn giản hơn: nếu có nhiều matches, show danh sách tất cả matches trực tiếp không cần quan tâm `asset_type`.

