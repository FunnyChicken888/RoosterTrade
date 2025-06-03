import json
import logging
import threading
import time
from typing import Dict, Optional
from queue import Queue

class TelegramCallbackHandler:
    def __init__(self):
        self.pending_trades: Dict[str, Dict] = {}  # 存儲待確認的交易
        self.confirmations: Dict[str, bool] = {}   # 存儲確認結果
        self.logger = logging.getLogger("telegram_handler")
        self._lock = threading.Lock()
        
    def add_pending_trade(self, strategy_name: str, trade_info: Dict) -> str:
        """添加待確認的交易"""
        with self._lock:
            trade_id = f"{strategy_name}_{int(time.time())}"
            self.pending_trades[trade_id] = trade_info
            self.confirmations[trade_id] = None
            return trade_id
            
    def confirm_trade(self, trade_id: str) -> None:
        """確認交易"""
        with self._lock:
            if trade_id in self.confirmations:
                self.confirmations[trade_id] = True
                self.logger.info(f"交易已確認: {trade_id}")
            
    def cancel_trade(self, trade_id: str) -> None:
        """取消交易"""
        with self._lock:
            if trade_id in self.confirmations:
                self.confirmations[trade_id] = False
                self.logger.info(f"交易已取消: {trade_id}")
                
    def wait_for_confirmation(self, trade_id: str, timeout: int = 300) -> Optional[bool]:
        """等待交易確認
        
        Args:
            trade_id: 交易ID
            timeout: 超時時間（秒）
            
        Returns:
            bool: True表示確認，False表示取消，None表示超時
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self._lock:
                if trade_id in self.confirmations:
                    result = self.confirmations[trade_id]
                    if result is not None:
                        # 清理已處理的交易
                        del self.pending_trades[trade_id]
                        del self.confirmations[trade_id]
                        return result
            time.sleep(1)  # 避免過度佔用CPU
            
        # 超時處理
        with self._lock:
            if trade_id in self.pending_trades:
                del self.pending_trades[trade_id]
            if trade_id in self.confirmations:
                del self.confirmations[trade_id]
        
        self.logger.warning(f"交易確認超時: {trade_id}")
        return None

# 全局實例
callback_handler = TelegramCallbackHandler()
