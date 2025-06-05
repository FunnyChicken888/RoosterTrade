import multiprocessing

# 綁定的 IP 和端口
bind = "0.0.0.0:5003"

# Worker 進程數量
# 一般建議：(CPU核心數 * 2) + 1
workers = 1

# Worker 類型
worker_class = "sync"

# 每個 worker 的執行緒數
threads = 4

# 超時設定
timeout = 120

# 最大請求數，超過後 worker 會重啟
max_requests = 2000
max_requests_jitter = 400

# 日誌配置
accesslog = "/app/log/gunicorn_access.log"
errorlog = "/app/log/gunicorn_error.log"
loglevel = "info"

# 預加載應用
preload_app = True

# 優雅的重啟時間
graceful_timeout = 120

# 保持連接
keepalive = 5
