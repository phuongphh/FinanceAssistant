# Issue #750

Add foreign stock provider (NVDA, IBM, ETF) — current providers only support VN stocks

# Issue: Không có provider cho cổ phiếu nước ngoài

**Nguyên nhân:** Tất cả cổ phiếu (VN và quốc tế) đều đi qua `stock_dispatcher` chỉ gồm VNDIRECT + SSI — 2 nguồn chỉ hỗ trợ chứng khoán Việt Nam.

**Cổ phiếu nước ngoài hiện có trong DB không được cập nhật giá:**
- `NVDA` (Mỹ) — updated 2026-05-03 (17 ngày không update)
- `IBM` (Mỹ) — updated 2026-05-03
- `TCEF` (ETF) — updated 2026-04-15 (hơn 1 tháng!)
- `E120` (ETF) — updated 2026-05-03

**Luồng hiện tại:**
```
stock_dispatcher → VNDIRECT (VN stocks) → fallback SSI (VN stocks)
                                                          ↓
                                             ❌ NVDA/IBM không có
```

**Yêu cầu:** Thêm provider cho cổ phiếu nước ngoài (Mỹ, ETF quốc tế) không cần API key, chỉ cần cover các cổ phiếu đang có trong portfolios của user (NVDA, IBM, TCEF, E120 và các stock nước ngoài khác user có thể thêm sau).

