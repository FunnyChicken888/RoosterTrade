import json
import logging
import requests

class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.logger = logging.getLogger("TelegramNotifier")

    def send_trade_confirmation(self, strategy_name: str, action: str, volume: float, coin_type: str, price: float, trade_id: str):
        """發送交易確認請求"""
        message = (
            f"⚠️ 交易確認請求\n\n"
            f"策略: {strategy_name}\n"
            f"操作: {action}\n"
            f"數量: {volume} {coin_type}\n"
            f"價格: {price} TWD\n"
            f"總額: {volume * price:.2f} TWD\n\n"
            f"請確認是否執行此交易？"
        )
        
        # 添加確認和取消按鈕，包含交易ID
        keyboard = {
            'inline_keyboard': [[
                {'text': '✅ 確認', 'callback_data': f'confirm_{trade_id}'},
                {'text': '❌ 取消', 'callback_data': f'cancel_{trade_id}'}
            ]]
        }
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            'chat_id': self.chat_id,
            'text': message,
            'parse_mode': 'HTML',
            'reply_markup': json.dumps(keyboard)
        }
        
        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
            return response.json()['result']['message_id']  # 返回消息ID以便後續更新
        except Exception as e:
            self.logger.error(f"發送交易確認請求失敗: {e}")
            return None

    def send_trade_result(self, strategy_name: str, success: bool, message: str):
        """發送交易結果通知"""
        status = "成功" if success else "失敗"
        text = f"策略: {strategy_name}\n交易狀態: {status}\n訊息: {message}"
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
        except Exception as e:
            self.logger.error(f"發送交易結果通知失敗: {e}")
