import os
import sys
import atexit

# 添加專案根目錄到 Python 路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)
sys.path.append(current_dir)

from frontend.app import app
from backend.services.telegram_bot import bot_service

def cleanup():
    """清理資源"""
    print("正在停止Telegram Bot服務...")
    bot_service.stop()

if __name__ == '__main__':
    # 註冊清理函數
    atexit.register(cleanup)
    
    # 啟動Telegram Bot服務
    try:
        bot_service.start()
        print("Telegram Bot服務已啟動")
    except Exception as e:
        print(f"啟動Telegram Bot服務失敗: {e}")
        sys.exit(1)
    
    # 啟動Flask應用，禁用重載功能
    app.run(host='0.0.0.0', debug=False, port=5003, use_reloader=False,threaded=True)
