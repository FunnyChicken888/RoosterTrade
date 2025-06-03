import os
import json
import logging
import datetime
import threading
from typing import List, Dict, Optional
from max.client_v3 import ClientV3
from ..models.strategy_config import TradingStrategyConfig
from .auto_trade_strategy import AutoTradeStrategy

class StrategyManager:
    def __init__(self, client: ClientV3):
        self.client = client
        self.strategies: Dict[str, AutoTradeStrategy] = {}
        self.logger = logging.getLogger("strategy_manager")
        self._strategy_lock = threading.Lock()  # 添加鎖機制
        self._load_all_strategies()

    def _load_all_strategies(self):
        """載入所有已保存的策略"""
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        strategy_dir = os.path.join(current_dir, "config", "strategies")
        if not os.path.exists(strategy_dir):
            os.makedirs(strategy_dir)
            return

        # 先載入所有策略配置
        for filename in os.listdir(strategy_dir):
            if filename.endswith('.json'):
                strategy_name = filename[:-5]  # 移除 .json 副檔名
                config = TradingStrategyConfig.load(strategy_name)
                if config and config.is_active:
                    strategy = AutoTradeStrategy(
                        self.client, 
                        config,
                        strategy_manager=self
                    )
                    # 確保交易記錄已經載入
                    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                    root_dir = os.path.join(root_dir, 'app')  # 添加 app 目錄
                    record_file = os.path.join(root_dir, "records", f"trading_records_{strategy_name}.json")
                    if os.path.exists(record_file):
                        strategy.trading_record.load_records()
                    self.strategies[strategy_name] = strategy

    def create_strategy(self, config: TradingStrategyConfig) -> bool:
        """創建新的交易策略"""
        try:
            if config.strategy_name in self.strategies:
                self.logger.error(f"策略 {config.strategy_name} 已存在")
                return False

            config.save()
            self.strategies[config.strategy_name] = AutoTradeStrategy(
                self.client, 
                config,
                strategy_manager=self
            )
            self.logger.info(f"成功創建策略: {config.strategy_name}")
            return True
        except Exception as e:
            self.logger.error(f"創建策略時發生錯誤: {e}")
            return False

    def update_strategy(self, config: TradingStrategyConfig) -> bool:
        """更新現有的交易策略"""
        try:
            if config.strategy_name not in self.strategies:
                self.logger.error(f"策略 {config.strategy_name} 不存在")
                return False

            config.save()
            self.strategies[config.strategy_name] = AutoTradeStrategy(
                self.client, 
                config,
                strategy_manager=self
            )
            self.logger.info(f"成功更新策略: {config.strategy_name}")
            return True
        except Exception as e:
            self.logger.error(f"更新策略時發生錯誤: {e}")
            return False

    def delete_strategy(self, strategy_name: str) -> bool:
        """刪除交易策略"""
        try:
            if strategy_name not in self.strategies:
                self.logger.error(f"策略 {strategy_name} 不存在")
                return False

            # 獲取根目錄路徑
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
            # 刪除策略配置文件
            config_file = os.path.join(root_dir, "config", "strategies", f"{strategy_name}.json")
            if os.path.exists(config_file):
                os.remove(config_file)

            # 備份並刪除交易記錄文件
            record_file = os.path.join(root_dir, "records", f"trading_records_{strategy_name}.json")
            if os.path.exists(record_file):
                # 確保備份目錄存在
                backup_dir = os.path.join(root_dir, "records_backup")
                if not os.path.exists(backup_dir):
                    os.makedirs(backup_dir)
                # 生成帶時間戳的備份文件名
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = os.path.join(backup_dir, f"trading_records_{strategy_name}_{timestamp}.json")
                # 移動文件到備份目錄
                os.rename(record_file, backup_file)
                self.logger.info(f"交易記錄已備份到: {backup_file}")

            del self.strategies[strategy_name]
            self.logger.info(f"成功刪除策略: {strategy_name}")
            return True
        except Exception as e:
            self.logger.error(f"刪除策略時發生錯誤: {e}")
            return False

    def get_strategy(self, strategy_name: str) -> Optional[AutoTradeStrategy]:
        """獲取指定的策略"""
        return self.strategies.get(strategy_name)

    def get_all_strategies(self) -> List[Dict]:
        """獲取所有策略的設定和當前狀態"""
        result = []
        for strategy in self.strategies.values():
            try:
                # 獲取當前市場數據
                current_balance = strategy.get_coin_balance()
                current_price = strategy.get_current_price()
                current_value = strategy.get_current_market_value()
                
                # 計算交易次數
                trade_records = strategy.trading_record.trade_records
                trade_count = len(trade_records)
                
                # 計算今日交易次數
                today_trade_count = strategy.trading_record.get_today_trade_count()
                
                # 計算已實現的套利金額（只考慮買賣差額）
                realized_profit = 0
                for record in trade_records:
                    if record['action'] == 'sell':
                        realized_profit += record['price'] * record['volume']
                    else:  # buy
                        realized_profit -= record['price'] * record['volume']
                
                # 計算當前持倉的市值
                current_position_value = current_balance * current_price
                
                # 計算總套利金額（已實現收益 + 當前持倉市值）
                net_profit = realized_profit + current_position_value

                # 計算買入和賣出觸發價格
                target_value = strategy.config.investment_amount
                auto_trade_percent = strategy.config.auto_trade_percent / 100  # 轉換為小數

                if current_balance > 0:
                    # 當有持倉時的觸發價格計算
                    buy_trigger_price = target_value * (1 - auto_trade_percent) / current_balance
                    sell_trigger_price = target_value * (1 + auto_trade_percent) / current_balance
                else:
                    # 當無持倉時，使用當前價格作為基準
                    buy_trigger_price = current_price * (1 - auto_trade_percent)
                    sell_trigger_price = current_price * (1 + auto_trade_percent)
                
                strategy_info = {
                    'config': strategy.config.__dict__,  # Convert to dict for JSON serialization
                    'current_balance': current_balance,
                    'current_price': current_price,
                    'current_value': current_value,
                    'trade_count': trade_count,
                    'today_trade_count': today_trade_count,
                    'net_profit': net_profit,
                    'buy_trigger_price': buy_trigger_price,
                    'sell_trigger_price': sell_trigger_price
                }
                result.append(strategy_info)
            except Exception as e:
                self.logger.error(f"獲取策略狀態時發生錯誤: {e}")
                strategy_info = {
                    'config': strategy.config.__dict__,  # Convert to dict for JSON serialization
                    'current_balance': 0,
                    'current_price': 0,
                    'current_value': 0,
                    'trade_count': 0,
                    'today_trade_count': 0,
                    'net_profit': 0,
                    'buy_trigger_price': 0,
                    'sell_trigger_price': 0
                }
                result.append(strategy_info)
        
        return result

    def enable_strategy(self, strategy_name: str) -> bool:
        """啟用策略"""
        try:
            strategy = self.strategies.get(strategy_name)
            if not strategy:
                self.logger.error(f"策略 {strategy_name} 不存在")
                return False
                
            strategy.config.is_active = True
            strategy.config.save()
            self.logger.info(f"已啟用策略: {strategy_name}")
            return True
        except Exception as e:
            self.logger.error(f"啟用策略時發生錯誤: {e}")
            return False
            
    def disable_strategy(self, strategy_name: str) -> bool:
        """停用策略"""
        try:
            strategy = self.strategies.get(strategy_name)
            if not strategy:
                self.logger.error(f"策略 {strategy_name} 不存在")
                return False
                
            strategy.config.is_active = False
            strategy.config.save()
            self.logger.info(f"已停用策略: {strategy_name}")
            return True
        except Exception as e:
            self.logger.error(f"停用策略時發生錯誤: {e}")
            return False
    
    def get_trading_history(self, strategy_name: Optional[str] = None) -> List[Dict]:
        """獲取交易歷史記錄"""
        all_records = []
        
        if strategy_name:
            strategy = self.strategies.get(strategy_name)
            if strategy:
                strategy.trading_record.refresh()
                records = strategy.trading_record.trade_records
                for record in records:
                    record['coin_type'] = strategy.config.coin_type
                all_records.extend(records)
        else:
            for strategy in self.strategies.values():
                strategy.trading_record.refresh()
                records = strategy.trading_record.trade_records
                for record in records:
                    record['coin_type'] = strategy.config.coin_type
                all_records.extend(records)
        
        all_records.sort(key=lambda x: x['trade_time'], reverse=True)
        return all_records
    
    def get_trading_stats(self, strategy_name: Optional[str] = None) -> Dict:
        """獲取交易統計數據"""
        if strategy_name:
            strategy = self.strategies.get(strategy_name)
            if not strategy:
                return {
                    'total_trades': 0,
                    'total_amount': 0,
                    'avg_amount': 0,
                    'net_profit': 0,
                    'current_position_value': 0,
                    'realized_profit': 0
                }
            records = strategy.trading_record.trade_records
            current_balance = strategy.get_coin_balance()
            current_price = strategy.get_current_price()
        else:
            records = []
            current_balance = 0
            current_price = 0
            for strategy in self.strategies.values():
                records.extend(strategy.trading_record.trade_records)
                current_balance += strategy.get_coin_balance()
                if current_price == 0:
                    current_price = strategy.get_current_price()

        total_trades = len(records)
        total_amount = sum(record['price'] * record['volume'] for record in records)
        avg_amount = total_amount / total_trades if total_trades > 0 else 0
        
        realized_profit = 0
        for record in records:
            if record['action'] == 'sell':
                realized_profit += record['price'] * record['volume']
            else:  # buy
                realized_profit -= record['price'] * record['volume']
        
        current_position_value = current_balance * current_price
        net_profit = realized_profit + current_position_value
        
        return {
            'total_trades': total_trades,
            'total_amount': total_amount,
            'avg_amount': avg_amount,
            'net_profit': net_profit,
            'current_position_value': current_position_value,
            'realized_profit': realized_profit
        }

    def execute_all_strategies(self) -> List[Dict]:
        """執行所有活躍的策略"""
        if not self._strategy_lock.acquire(blocking=False):
            self.logger.info("另一個策略執行正在進行中，跳過本次執行")
            return []

        try:
            results = []
            for strategy_name, strategy in self.strategies.items():
                if strategy.config.is_active:
                    self.logger.info(f"開始執行策略: {strategy_name}")
                    
                    take_profit_result = strategy.check_take_profit()
                    if take_profit_result:
                        results.append({
                            "strategy_name": strategy_name,
                            "action": "take_profit",
                            "message": take_profit_result
                        })
                        continue

                    trade_result = strategy.check_and_trade()
                    if trade_result:
                        results.append({
                            "strategy_name": strategy_name,
                            "action": "trade",
                            "message": trade_result
                        })
                    
                    self.logger.info(f"完成策略執行: {strategy_name}")

            return results
        finally:
            self._strategy_lock.release()
