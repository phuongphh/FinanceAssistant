# Issue #706

Stock market data: VNDIRECT 403 (missing User-Agent), SSI 502

# Issue #704 — Stock market data: VNDIRECT 403 (missing User-Agent), SSI 502

## Nguyên nhân

Cả 2 provider SSI và VNDIRECT đều dùng `httpx.AsyncClient` **không set User-Agent header**:

- `backend/market_data/providers/stock_vndirect.py:63` — `httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)`
- `backend/market_data/providers/stock_ssi.py:37-38` — `httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)`

Hậu quả: httpx gửi request với User-Agent mặc định (`python-httpx/<version>`), bị API chặn (403).

### VNDIRECT

`/v4/stock_prices` — trả 403 với httpx mặc định, 200 OK khi set User-Agent trình duyệt. API đã thêm bot protection.

### SSI

`/1.1/defaultAllStocks` — trả 502 bất kể User-Agent là gì. Server đang bảo trì hoặc endpoint đã thay đổi.

## Ảnh hưởng

- Stock market data không fetch được cho bất kỳ mã chứng khoán nào
- Morning briefing thiếu thông tin giá cổ phiếu
- Twin engine dùng user input price thay vì market price
- Circuit breaker mở cho cả 2 provider sau 5 lần fail liên tiếp

## Gợi ý

- Thêm `headers={"User-Agent": "Mozilla/5.0..."}` vào httpx client
- SSI endpoint có thể đã thay đổi — cần kiểm tra lại docs của SSI iBoard

