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

# Đảm bảo Python nhận diện thư mục /app để import được package backend
ENV PYTHONPATH=/app

# Mặc định chạy API (sẽ được override bởi command trong docker-compose nếu cần)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]