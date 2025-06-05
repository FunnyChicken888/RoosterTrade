import json
import logging
import threading
from typing import Dict, Optional
import requests
from ..utils.telegram_handler import callback_handler
import os

class TelegramBotService:
    def __init__(self):
        self.logger = logging.getLogger("telegram_bot")
        self._running = False
        self._thread = None
        
        # 載入配置
        try:
            # 使用環境變量或預設路徑
            config_path = os.getenv('CONFIG_PATH', '/app/config/config.json')
            self.logger.info(f"使用配置文件: {config_path}")
            
            if not os.path.exists(config_path):
                self.logger.error(f"配置文件不存在: {config_path}")
                raise FileNotFoundError(f"配置文件不存在: {config_path}")

            with open(config_path, 'r') as f:
                config = json.load(f)
                self.bot_token = config.get('telegram_bot_token')
                self.chat_id = config.get('telegram_chat_id')
                
                if not self.bot_token or not self.chat_id:
                    raise ValueError("配置文件缺少必要的 Telegram 參數")
        except Exception as e:
            self.logger.error(f"載入Telegram配置失敗: {e}")
            # 設置預設值，避免應用程式崩潰
            self.bot_token = None
            self.chat_id = None
            self.logger.warning("Telegram Bot 服務將無法啟動，但不影響其他功能")
            
    def _get_updates(self, offset: Optional[int] = None) -> list:
        """獲取Telegram更新"""
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        params = {
            'timeout': 30,
            'allowed_updates': ['callback_query']
        }
        if offset:
            params['offset'] = offset
            
        try:
            response = requests.get(url, params=params)
            return response.json().get('result', [])
        except Exception as e:
            self.logger.error(f"獲取Telegram更新失敗: {e}")
            return []
            
    def _handle_callback_query(self, query: Dict):
        """處理回調查詢"""
        try:
            callback_data = query['data']
            message_id = query['message']['message_id']
            
            # 解析回調數據
            action, trade_id = callback_data.split('_', 1)
            
            # 根據動作更新交易狀態
            if action == 'confirm':
                callback_handler.confirm_trade(trade_id)
                response_text = "✅ 交易已確認"
            else:  # cancel
                callback_handler.cancel_trade(trade_id)
                response_text = "❌ 交易已取消"
                
            # 更新消息
            url = f"https://api.telegram.org/bot{self.bot_token}/editMessageText"
            data = {
                'chat_id': self.chat_id,
                'message_id': message_id,
                'text': response_text,
                'parse_mode': 'HTML'
            }
            requests.post(url, json=data)
            
            # 回應回調查詢
            url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
            data = {
                'callback_query_id': query['id'],
                'text': response_text
            }
            requests.post(url, json=data)
            
        except Exception as e:
            self.logger.error(f"處理回調查詢失敗: {e}")
            
    def _polling_loop(self):
        """輪詢更新"""
        last_update_id = None
        
        while self._running:
            try:
                updates = self._get_updates(last_update_id)
                for update in updates:
                    if 'callback_query' in update:
                        self._handle_callback_query(update['callback_query'])
                    if update['update_id'] >= (last_update_id or 0):
                        last_update_id = update['update_id'] + 1
            except Exception as e:
                self.logger.error(f"輪詢更新時發生錯誤: {e}")
                
    def start(self):
        """啟動bot服務"""
        if self._thread is not None:
            return
            
        if not self.bot_token or not self.chat_id:
            self.logger.warning("缺少 Telegram 配置，Bot 服務無法啟動")
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._polling_loop)
        self._thread.daemon = True
        self._thread.start()
        self.logger.info("Telegram Bot服務已啟動")
        
    def stop(self):
        """停止bot服務"""
        self._running = False
        if self._thread:
            self._thread.join()
            self._thread = None
        self.logger.info("Telegram Bot服務已停止")

# 全局實例
bot_service = TelegramBotService()
