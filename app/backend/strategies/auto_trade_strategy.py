import logging
import json
import datetime
import os
from typing import Optional
from ..models.strategy_config import TradingStrategyConfig
from ..utils.trading_record import TradingRecord
from ..utils.notification import TelegramNotifier
from ..utils.telegram_handler import callback_handler
from max.client_v3 import ClientV3

class AutoTradeStrategy:
    def __init__(self, client: ClientV3, config: TradingStrategyConfig, strategy_manager=None):
        self.client = client
        self.config = config
        self.logger = logging.getLogger(f"strategy.{config.strategy_name}")
        self.trading_record = TradingRecord(config.strategy_name)
        self.strategy_manager = strategy_manager
        
        # 初始化Telegram通知
        try:
            # 獲取當前文件的目錄路徑
            current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config_path = os.path.join(current_dir, 'config', 'config.json')
            config_path = os.path.abspath(config_path)
            
            self.logger.info(f"正在嘗試讀取配置文件: {config_path}")
            
            if not os.path.exists(config_path):
                self.logger.error(f"配置文件不存在: {config_path}")
                raise FileNotFoundError(f"配置文件不存在: {config_path}")

            with open(config_path, 'r') as f:
                config_data = json.load(f)
                self.notifier = TelegramNotifier(
                    config_data['telegram_bot_token'],
                    config_data['telegram_chat_id']
                )
        except Exception as e:
            self.logger.error(f"初始化Telegram通知失敗: {e}")
            self.notifier = None
    
    def get_current_market_value(self) -> Optional[float]:
        """獲取當前市值，如果發生錯誤返回None"""
        try:
            price = self.get_current_price()
            return self.trading_record.get_current_market_value(price)
        except Exception as e:
            self.logger.error(f"計算市值時發生錯誤: {e}")
            return None

    def get_current_price(self) -> float:
        """獲取當前價格"""
        try:
            market = f"{self.config.coin_type.lower()}twd"
            trades = self.client.get_trades(market, limit=1)
            if trades and len(trades) > 0:
                return float(trades[0]['price'])
            raise ValueError(f"無法獲取{market}的最新成交價格")
        except Exception as e:
            self.logger.error(f"獲取價格時發生錯誤: {market} - {e}")
            raise

    def get_coin_balance(self) -> float:
        """獲取幣種餘額"""
        return self.trading_record.get_current_balance()

    def execute_trade(self, action: str, volume: float, force_confirm: bool = False) -> bool:
        """執行交易"""
        try:
            market = f"{self.config.coin_type.lower()}twd"
            current_price = self.get_current_price()
            trade_amount = volume * current_price
            
            # 檢查交易條件
            need_confirm, reason = self.trading_record.check_trade_conditions(
                trade_amount,
                self.config.daily_trade_limit,
                self.config.confirm_amount_threshold
            )
            
            # 如果是買入操作，檢查TWD餘額
            if action == 'buy':
                # 計算所需的TWD金額
                required_twd = volume * current_price
                # 獲取TWD餘額
                balances = self.client.get_account_balance()
                twd_balance = 0
                for balance in balances:
                    if balance['currency'] == 'twd':
                        twd_balance = float(balance['balance'])
                        break
                
                # 檢查餘額是否足夠
                if twd_balance < required_twd:
                    error_msg = f"TWD餘額不足。需要: {required_twd:.2f} TWD，當前餘額: {twd_balance:.2f} TWD"
                    self.logger.error(error_msg)
                    if self.notifier:
                        self.notifier.send_trade_result(self.config.strategy_name, False, error_msg)
                    return False

            # 如果需要確認或強制確認，發送交易確認請求
            if need_confirm or force_confirm:
                # 準備交易信息
                trade_info = {
                    'strategy_name': self.config.strategy_name,
                    'action': action,
                    'volume': volume,
                    'coin_type': self.config.coin_type,
                    'price': current_price,
                    'total_amount': trade_amount,
                    'reason': reason if need_confirm else None
                }
                
                # 添加到待確認隊列
                trade_id = callback_handler.add_pending_trade(
                    self.config.strategy_name, 
                    trade_info
                )
                
                # 發送確認請求，傳入trade_id
                self.notifier.send_trade_confirmation(
                    self.config.strategy_name,
                    action,
                    volume,
                    self.config.coin_type,
                    current_price,
                    trade_id
                )
                
                self.logger.info("已發送交易確認請求，等待用戶確認...")
                
                # 等待用戶確認（最多等待5分鐘）
                confirmation = callback_handler.wait_for_confirmation(trade_id, timeout=300)
                
                if confirmation is None:
                    error_msg = "交易確認超時，取消交易"
                    self.logger.warning(error_msg)
                    if self.notifier:
                        self.notifier.send_trade_result(
                            self.config.strategy_name,
                            False,
                            error_msg
                        )
                    return False
                    
                if not confirmation:
                    error_msg = "用戶取消交易"
                    self.logger.info(error_msg)
                    if self.notifier:
                        self.notifier.send_trade_result(
                            self.config.strategy_name,
                            False,
                            error_msg
                        )
                    return False

            # 用戶確認後執行交易
            result = self.client.create_order(
                market=market,
                side=action,
                volume=volume,
                order_type='market'
            )
            
            # 交易成功後記錄
            self.trading_record.add_trade_record(
                datetime.datetime.now().isoformat(),
                current_price,
                volume,
                action,
                confirmed=need_confirm
            )
            
            success_msg = f"執行{action}交易: {volume} {self.config.coin_type}"
            self.logger.info(success_msg)
            
            # 發送交易結果通知
            if self.notifier:
                self.notifier.send_trade_result(
                    self.config.strategy_name,
                    True,
                    success_msg
                )
            
            return True
        except Exception as e:
            error_msg = f"執行交易時發生錯誤: {e}"
            self.logger.error(error_msg)
            if self.notifier:
                self.notifier.send_trade_result(
                    self.config.strategy_name,
                    False,
                    error_msg
                )
            return False

    def check_and_trade(self) -> Optional[str]:
        """檢查並執行交易策略"""
        try:
            current_value = self.get_current_market_value()
            if current_value is None:
                self.logger.error("無法獲取當前市值，跳過交易檢查")
                return None
                
            target_value = self.config.investment_amount
            current_balance = self.get_coin_balance()
            
            # 計算偏差百分比
            if current_balance == 0:
                deviation_percent = 100  # 完全沒有持倉時
            else:
                deviation_percent = abs((current_value - target_value) / target_value * 100)
            
            # 如果偏差超過設定的自動交易百分比，執行交易
            if deviation_percent > self.config.auto_trade_percent:
                if current_value < target_value:
                    # 需要買入
                    buy_amount = target_value - current_value
                    
                    # 如果是首次建倉（完全沒有持倉），強制發送Telegram確認
                    if current_balance == 0:
                        self.logger.info("首次建倉，需要Telegram確認")
                        volume = buy_amount / self.get_current_price()
                        if self.execute_trade('buy', volume, force_confirm=True):
                            return f"執行首次建倉買入: {volume} {self.config.coin_type}"
                        return None
                    
                    # 非首次建倉，檢查是否超過加倉上限
                    net_investment = self.trading_record.get_net_investment()
                    if net_investment >= self.config.investment_amount + self.config.max_position:
                        self.logger.info(f"已達加倉上限 {self.config.max_position}，等待市場回升")
                        return None
                    
                    volume = buy_amount / self.get_current_price()
                    if self.execute_trade('buy', volume):
                        return f"執行買入: {volume} {self.config.coin_type}"
                else:
                    # 需要賣出
                    sell_amount = current_value - target_value
                    volume = sell_amount / self.get_current_price()
                    if self.execute_trade('sell', volume):
                        return f"執行賣出: {volume} {self.config.coin_type}"
            
            return None
        except Exception as e:
            self.logger.error(f"策略執行時發生錯誤: {e}")
            return None

    def check_take_profit(self) -> Optional[str]:
        """檢查是否達到停利條件"""
        try:
            current_value = self.get_current_market_value()
            if current_value is None:
                self.logger.error("無法獲取當前市值，跳過停利檢查")
                return None
                
            if current_value >= self.config.take_profit:
                # 全部賣出
                balance = self.get_coin_balance()
                if balance > 0 and self.execute_trade('sell', balance):
                    # 停利後自動停用策略
                    if self.strategy_manager:
                        self.strategy_manager.disable_strategy(self.config.strategy_name)
                        message = f"達到停利條件，賣出全部持倉: {balance} {self.config.coin_type}，策略已自動停用"
                    else:
                        message = f"達到停利條件，賣出全部持倉: {balance} {self.config.coin_type}"
                    
                    # 發送通知
                    if self.notifier:
                        self.notifier.send_trade_result(
                            self.config.strategy_name,
                            True,
                            message
                        )
                    
                    return message
            return None
        except Exception as e:
            self.logger.error(f"檢查停利時發生錯誤: {e}")
            return None
