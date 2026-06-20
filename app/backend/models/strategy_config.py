import os
import logging
from dataclasses import dataclass, field
from typing import Optional
import json
from datetime import datetime

from ..utils.paths import strategies_dir

logger = logging.getLogger("strategy_config")


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
    # 用 default_factory，否則 dataclass 會在「載入模組時」就把時間固定下來，
    # 造成所有策略的建立時間都一樣。
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
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
        filename = os.path.join(strategies_dir(), f"{self.strategy_name}.json")
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=4)

    @classmethod
    def load(cls, strategy_name: str) -> Optional['TradingStrategyConfig']:
        """從檔案載入策略設定"""
        try:
            filename = os.path.join(strategies_dir(), f"{strategy_name}.json")
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return cls(**data)
        except FileNotFoundError:
            return None
