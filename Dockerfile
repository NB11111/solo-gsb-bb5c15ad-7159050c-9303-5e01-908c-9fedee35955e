FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    AUDIT_DB_PATH=/data/audit.db

WORKDIR /app

# 先装依赖，利用构建缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 数据库持久化目录（启动时自动建库建表）
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# 固定 8000 端口；应用启动时 lifespan 自动初始化数据库
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
