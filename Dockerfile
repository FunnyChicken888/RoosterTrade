# 使用 Python 3.9 作為基礎鏡像
FROM python:3.9-slim

# 設置時區為台北時間
ENV TZ=Asia/Taipei

# 設置工作目錄
WORKDIR /app

# 複製 requirements.txt
COPY requirements.txt .

# 安裝依賴
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式代碼
COPY app/ .

# 創建必要的目錄
RUN mkdir -p log records config

# 設置環境變量
ENV PYTHONPATH=/app
ENV FLASK_APP=frontend.app
ENV FLASK_ENV=production

# 暴露端口
EXPOSE 5000

# 運行應用
CMD ["python", "run.py"]
