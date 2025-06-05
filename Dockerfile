# 使用 Python 3.9 作為基礎鏡像
FROM python:3.9-slim

# 設置時區為台北時間
ENV TZ=Asia/Taipei

# 設置工作目錄
WORKDIR /app

# 複製所有必要文件
COPY requirements.txt gunicorn.conf.py ./
COPY app/ ./

# 安裝依賴
RUN pip install --no-cache-dir -r requirements.txt

# 創建必要的目錄
RUN mkdir -p log records config

# 設置環境變量
ENV PYTHONPATH=/app
ENV FLASK_APP=frontend.app
ENV FLASK_ENV=production

# 暴露端口
EXPOSE 5003

# 使用 Gunicorn 運行應用
CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:application"]
