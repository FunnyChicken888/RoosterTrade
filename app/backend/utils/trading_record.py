import os
import json
import datetime
from typing import Tuple

class TradingRecord:
    def __init__(self, strategy_name):
        self.strategy_name = strategy_name
        self.creation_time = datetime.datetime.now().isoformat()
        self.trade_records = []
        # 獲取專案根目錄的絕對路徑
        self.root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
   
        # 確保記錄目錄存在
        self.records_dir = os.path.join(self.root_dir, "records")
        if not os.path.exists(self.records_dir):
            os.makedirs(self.records_dir)
            
        self.filename = os.path.join(self.records_dir, f"trading_records_{strategy_name}.json")
        self.load_records()  # 初始化時載入已有記錄
    
    def load_records(self):
        """載入策略的交易記錄"""
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.trade_records = data.get('trade_records', [])
        except FileNotFoundError:
            self.trade_records = []
    
    def refresh(self):
        """重新從文件載入記錄"""
        self.load_records()
    
    def add_trade_record(self, trade_time, price, volume, action, confirmed=False):
        """添加交易記錄"""
        record = {
            'strategy_name': self.strategy_name,
            'trade_time': trade_time,
            'price': price,
            'volume': volume,
            'action': action,
            'confirmed': confirmed,  # 是否經過Telegram確認
            'amount': price * volume  # 交易金額
        }
        self.trade_records.append(record)
        self.save_to_json()  # 每次交易後立即保存
    
    def get_current_balance(self):
        """計算當前持有餘額"""
        balance = 0.0
        for record in self.trade_records:
            if record['action'] == 'buy':
                balance += record['volume']
            elif record['action'] == 'sell':
                balance -= record['volume']
        return balance

    def get_net_investment(self):
        """計算淨投資金額（買入金額總和減去賣出金額總和）"""
        net_investment = 0.0
        for record in self.trade_records:
            amount = record['price'] * record['volume']
            if record['action'] == 'buy':
                net_investment += amount
            elif record['action'] == 'sell':
                net_investment -= amount
        return net_investment

    def get_current_market_value(self, current_price):
        """計算當前市值"""
        balance = self.get_current_balance()
        return balance * current_price

    def get_today_trade_count(self):
        """獲取今日交易次數"""
        today = datetime.datetime.now().date()
        count = 0
        for record in self.trade_records:
            trade_date = datetime.datetime.fromisoformat(record['trade_time']).date()
            if trade_date == today:
                count += 1
        return count

    def check_trade_conditions(self, amount: float, daily_limit: int, amount_threshold: float) -> Tuple[bool, str]:
        """檢查交易條件
        
        Args:
            amount: 交易金額
            daily_limit: 每日交易次數限制
            amount_threshold: 需要確認的金額閾值
            
        Returns:
            Tuple[bool, str]: (是否需要確認, 原因)
        """
        # 檢查每日交易次數
        today_count = self.get_today_trade_count()
        if today_count >= daily_limit:
            return True, f"已達每日交易次數限制 ({today_count}/{daily_limit})"
            
        # 檢查交易金額
        if amount_threshold > 0 and amount >= amount_threshold:
            return True, f"交易金額 ({amount:.2f}) 超過閾值 ({amount_threshold:.2f})"
            
        return False, ""

    def save_to_json(self):
        """保存交易記錄到特定策略的JSON文件"""
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump({
                'strategy_name': self.strategy_name,
                'creation_time': self.creation_time,
                'trade_records': self.trade_records
            }, f, ensure_ascii=False, indent=4)
