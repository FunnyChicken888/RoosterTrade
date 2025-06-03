import os
import logging
from dataclasses import dataclass
from typing import Optional
import json
from datetime import datetime

# 獲取專案根目錄的絕對路徑
current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logger = logging.getLogger("strategy_config")
logger.info(f"專案根目錄路徑: {current_dir}")


@dataclass
class TradingStrategyConfig:
    strategy_name: str
    investment_amount: float  # 投資金額
    max_position: float      # 加倉金額上限
    take_profit: float      # 停利金額
    auto_trade_percent: float  # 自動交易%
    coin_type: str          # 投資幣種
    daily_trade_limit: int = 5  # 每日自動交易次數限制
    confirm_amount_threshold: float = 0  # 需要確認的交易金額閾值
    is_active: bool = True
    created_at: str = datetime.now().isoformat()
    
    def to_dict(self):
        return {
            "strategy_name": self.strategy_name,
            "investment_amount": self.investment_amount,
            "max_position": self.max_position,
            "take_profit": self.take_profit,
            "auto_trade_percent": self.auto_trade_percent,
            "coin_type": self.coin_type,
            "daily_trade_limit": self.daily_trade_limit,
            "confirm_amount_threshold": self.confirm_amount_threshold,
            "is_active": self.is_active,
            "created_at": self.created_at
        }
    
    def save(self):
        """將策略設定儲存到檔案"""
        filename = os.path.join(current_dir, "config", "strategies", f"{self.strategy_name}.json")
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=4)
    
    @classmethod
    def load(cls, strategy_name: str) -> Optional['TradingStrategyConfig']:
        """從檔案載入策略設定"""
        try:
            filename = os.path.join(current_dir, "config", "strategies", f"{strategy_name}.json")
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return cls(**data)
        except FileNotFoundError:
            return None
