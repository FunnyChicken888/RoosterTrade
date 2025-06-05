import os
import sys
import atexit

# 添加專案根目錄到 Python 路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, current_dir)
sys.path.insert(0, project_root)

# 設置 PYTHONPATH 環境變數
os.environ['PYTHONPATH'] = f"{current_dir}:{project_root}"

from frontend.app import app
from backend.services.telegram_bot import bot_service

def cleanup():
    """清理資源"""
    print("正在停止Telegram Bot服務...")
    bot_service.stop()

# 註冊清理函數
atexit.register(cleanup)

# 啟動Telegram Bot服務
try:
    bot_service.start()
    print("Telegram Bot服務已啟動")
except Exception as e:
    print(f"啟動Telegram Bot服務失敗: {e}")

# 導出 application
application = app

if __name__ == "__main__":
    app.run()
