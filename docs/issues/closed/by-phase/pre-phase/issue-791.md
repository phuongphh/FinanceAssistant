# Issue #791

Admin portal SPA routes return 404 — Starlette StaticFiles html=True does not fallback to index.html

# Issue: Admin portal SPA routing không hoạt động — Starlette StaticFiles không fallback index.html

**Nguyên nhân:** FastAPI mount admin static files ở "/" với `html=True`. Nhưng Starlette 0.49.3 chỉ fallback index.html nếu path là thư mục hoặc file `.html`, không fallback cho tất cả SPA routes.

**Tác động:** Tất cả path admin ngoại trừ "/" đều trả 404 JSON:
```
/login  → 404 Not Found
/admin  → 404 Not Found
/anything → 404 Not Found
/       → 200 OK ✅ (chỉ root)
```

**File hiện tại:** backend/main.py dòng 333-336:
```python
_ADMIN_STATIC = Path(__file__).parent / "static" / "admin"
if _ADMIN_STATIC.exists():
    app.mount("/", StaticFiles(directory=str(_ADMIN_STATIC), html=True), name="admin-spa")
```

**Fix cần:** Thay StaticFiles bằng SPAStaticFiles (subclass có fallback về index.html khi 404):

```python
class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as ex:
            if ex.status_code == 404:
                return await super().get_response("index.html", scope)
            raise
```

**Ghi chú:** Đây là vấn đề đã biết với Starlette < 0.50, fix phổ biến là SPAStaticFiles.

