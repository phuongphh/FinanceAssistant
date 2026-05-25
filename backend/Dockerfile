# =============================================================================
# Stage 1: build admin SPA (betien-admin)
# =============================================================================
# Build SPA NGAY TRONG image — host prod KHÔNG cần node/npm (deploy chạy trong
# namespace không có npm). Trước đây script build trên host rồi mới docker build;
# cách đó fail "npm: command not found". Multi-stage chỉ cần docker trên host.
FROM node:22-slim AS admin-build
WORKDIR /admin

# Cài deps trước (tách layer để cache khi source đổi mà deps không đổi).
COPY betien-admin/package.json betien-admin/package-lock.json ./
RUN npm install

# Source + build. VITE_API_BASE là build-time config (vite chỉ inline VITE_*),
# truyền vào qua compose build.args (đọc từ .env), fallback domain prod.
COPY betien-admin/ ./
ARG VITE_API_BASE=https://admin.betien.vn/api/admin
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build
# → /admin/dist

# =============================================================================
# Stage 2: backend runtime (Python)
# =============================================================================
FROM python:3.11-slim

# Thiết lập thư mục làm việc gốc trong container
WORKDIR /app

# Cài đặt thư viện hệ thống cần thiết cho Postgres và build tool
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy file requirements từ folder backend của host vào container
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ nội dung thư mục FinanceAssistant vào /app
# Điều này sẽ tạo ra cấu trúc /app/backend/... bên trong container
COPY . .

# Admin SPA đã build từ stage 1 → đúng nơi backend serve (_ADMIN_STATIC =
# backend/static/admin, mount tại "/"). Đặt SAU `COPY . .` để ghi đè thư mục
# rỗng/cũ từ context (backend/static/admin bị gitignore nên context không có).
COPY --from=admin-build /admin/dist /app/backend/static/admin

# Đảm bảo Python nhận diện thư mục /app để import được package backend
ENV PYTHONPATH=/app

# Mặc định chạy API (sẽ được override bởi command trong docker-compose nếu cần)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
