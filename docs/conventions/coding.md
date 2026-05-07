## Coding Conventions

### Python
- **async/await** cho tất cả I/O (DB, API, file)
- Type hints bắt buộc
- Pydantic cho data validation
- Exception handling: raise cụ thể, không swallow silently
- **Logging**: Python `logging` module, không `print()`

### Money Handling ⭐ CRITICAL cho V2
- **LUÔN dùng `Decimal`**, không dùng `float` cho money
- Import: `from decimal import Decimal`
- DB columns: `NUMERIC(20, 2)` cho money, `NUMERIC(15, 2)` cho amount nhỏ
- Format output qua `currency_utils.format_money_short/full`

### API Design
- Response format thống nhất:
```python
{"data": {...}, "error": null}
{"data": null, "error": {"code": "ASSET_NOT_FOUND", "message": "..."}}
```
- HTTP status codes chuẩn: 200, 201, 400, 401, 404, 422, 500
- Tất cả endpoints nhận `user_id` qua API key lookup / JWT

### Security
- **KHÔNG** hardcode credentials
- **KHÔNG** commit `.env`
- Secrets qua env vars + `config.py`
- SQLAlchemy ORM hoặc parameterized queries
- ⭐ V2: Wealth data sensitivity cao — consider encryption-at-rest cho `assets.current_value` khi scale

### Content Files (YAML) ⭐ NEW V2
- User-facing messages → YAML files trong `content/`
- Dễ edit không cần deploy
- Test content bằng cách đọc to — nếu sến súa, rewrite

### Testing
- Unit test cho mỗi service method
- **Integration test cho LLM prompts** (critical cho storytelling)
- Prompt test suite: 30+ sample inputs với expected outputs
- Mỗi wizard cần end-to-end test
