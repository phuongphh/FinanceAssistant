# Issue #14

[Feature] Investment Portfolio Management & Income Tracking

## Overview
Implement a comprehensive investment portfolio management system that allows users to track all financial assets and monitor both active and passive income streams.

---

## Requirements

### 1. Portfolio Management

#### Supported Asset Types:

| Asset Type | Loại tài sản | Key fields |
|------------|-------------|------------|
| `real_estate` | Bất động sản | Địa chỉ, diện tích, giá mua, giá thị trường, cho thuê hay không |
| `stocks` | Chứng khoán | Mã CK, sàn (HOSE/HNX), số lượng, giá mua TB, giá hiện tại |
| `mutual_fund` | Chứng chỉ quỹ | Tên quỹ, NAV mua vào, NAV hiện tại, số đơn vị |
| `crypto` | Tiền số | Loại coin/token, số lượng, giá mua TB, giá hiện tại |
| `life_insurance` | Bảo hiểm nhân thọ | Tên công ty, số hợp đồng, mệnh giá, phí đóng hàng năm, ngày đáo hạn |
| `gold` | Vàng | Loại (SJC/nhẫn), số lượng (chỉ/gram), giá mua, giá hiện tại |

#### Portfolio Features:
- Thêm / sửa / xóa tài sản
- Xem tổng giá trị danh mục theo thời gian thực
- Hiển thị P&L (lãi/lỗ) cho từng tài sản và toàn danh mục
- Phân bổ tài sản (asset allocation) theo loại — biểu đồ tròn
- Cập nhật giá thị trường: tự động (stocks, crypto, gold) hoặc thủ công (real estate, insurance)

---

### 2. Income Tracking

#### Thu nhập chủ động (Active Income):
- **Tiền lương / thu nhập từ công việc**
- Nhập thủ công hàng tháng
- Hiển thị theo tháng/quý/năm

#### Thu nhập thụ động (Passive Income):

| Nguồn | Loại tài sản gốc | Ghi chú |
|-------|-----------------|---------|
| Cổ tức chứng khoán | `stocks` | Auto-link với portfolio |
| Lợi nhuận quỹ | `mutual_fund` | Auto-link với portfolio |
| Staking/yield crypto | `crypto` | Nhập thủ công hoặc auto |
| Tiền lãi bảo hiểm | `life_insurance` | Nhập thủ công |
| Thu nhập cho thuê BĐS | `real_estate` | Nhập thủ công hàng tháng |
| Lãi từ vàng (khi bán) | `gold` | Tính tự động khi realized |

#### Income Dashboard:
- Tổng thu nhập chủ động vs thụ động theo tháng/năm
- Tỷ lệ passive income / total income (%) — mục tiêu tài chính tự do
- Biểu đồ xu hướng thu nhập theo thời gian

---

### 3. Data Model

```sql
-- Bảng tài sản
CREATE TABLE IF NOT EXISTS portfolio_assets (
  id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID          NOT NULL REFERENCES user_profiles(id),
  asset_type      VARCHAR(30)   NOT NULL,  -- real_estate|stocks|mutual_fund|crypto|life_insurance|gold
  name            VARCHAR(200)  NOT NULL,  -- Tên tài sản
  quantity        DECIMAL(20,6),           -- Số lượng (cổ phiếu, coin, chỉ vàng...)
  purchase_price  DECIMAL(15,0),           -- Giá mua (VND)
  current_price   DECIMAL(15,0),           -- Giá hiện tại (VND)
  metadata        JSONB,                   -- Thông tin bổ sung theo từng loại tài sản
  created_at      TIMESTAMP     DEFAULT NOW(),
  updated_at      TIMESTAMP     DEFAULT NOW()
);

-- Bảng thu nhập
CREATE TABLE IF NOT EXISTS income_records (
  id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID          NOT NULL REFERENCES user_profiles(id),
  income_type     VARCHAR(20)   NOT NULL,  -- 'active' | 'passive'
  source          VARCHAR(50)   NOT NULL,  -- salary|dividend|rental|crypto_yield|insurance|gold
  asset_id        UUID          REFERENCES portfolio_assets(id),  -- NULL nếu active income
  amount          DECIMAL(15,0) NOT NULL,
  period          DATE          NOT NULL,  -- Ngày đầu tháng
  note            TEXT,
  created_at      TIMESTAMP     DEFAULT NOW()
);
```

---

### 4. Bot Commands / Natural Language Triggers

- *"danh mục đầu tư của tôi"* → hiển thị tổng quan portfolio
- *"thêm 100 cổ phiếu VNM giá 80,000"* → thêm vào portfolio
- *"thu nhập tháng này"* → báo cáo income tháng hiện tại
- *"tỷ lệ passive income của tôi là bao nhiêu"* → tính tỷ lệ passive/total

---

## Acceptance Criteria
- [ ] CRUD đầy đủ cho tất cả 6 loại tài sản
- [ ] Tổng giá trị danh mục tính đúng theo giá hiện tại
- [ ] P&L hiển thị đúng cho từng tài sản và toàn danh mục
- [ ] Phân loại thu nhập chủ động / thụ động chính xác
- [ ] Tỷ lệ passive income được tính đúng
- [ ] Bot nhận diện được natural language triggers cơ bản
- [ ] Báo cáo income theo tháng/quý/năm hoạt động đúng
