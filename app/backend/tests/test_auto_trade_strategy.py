import unittest
from unittest.mock import Mock, patch
import os
from datetime import datetime
from ..strategies.auto_trade_strategy import AutoTradeStrategy
from ..models.strategy_config import TradingStrategyConfig
from max.client import Client

class TestAutoTradeStrategy(unittest.TestCase):
    def setUp(self):
        # 模擬MAX API客戶端
        self.mock_client = Mock(spec=Client)
        
        # 設置策略配置
        self.config = TradingStrategyConfig(
            strategy_name="test_strategy",
            coin_type="BTC",
            investment_amount=10000.0,
            auto_trade_percent=5.0,
            take_profit=12000.0,
            max_position=20000.0
        )
        
        # 創建策略實例
        self.strategy = AutoTradeStrategy(self.mock_client, self.config)
        
        # 清理可能存在的測試文件
        self.test_file = f"trading_records_{self.config.strategy_name}.json"
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
    
    def tearDown(self):
        # 清理測試文件
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
    
    def test_get_current_price(self):
        """測試獲取當前價格"""
        # 模擬API響應
        self.mock_client.get_public_markets_summary.return_value = {
            'tickers': {
                'BTCtwd': {
                    'last': '500000'
                }
            }
        }
        
        price = self.strategy.get_current_price()
        self.assertEqual(price, 500000.0)
        self.mock_client.get_public_markets_summary.assert_called_once()
    
    def test_execute_trade_buy(self):
        """測試執行買入交易"""
        # 模擬API響應
        self.mock_client.set_private_create_order.return_value = {'id': '12345'}
        self.mock_client.get_public_markets_summary.return_value = {
            'tickers': {
                'BTCtwd': {
                    'last': '500000'
                }
            }
        }
        
        # 執行買入交易
        result = self.strategy.execute_trade('buy', 1.0)
        
        # 驗證交易執行
        self.assertTrue(result)
        self.mock_client.set_private_create_order.assert_called_once_with(
            'BTCtwd', 'buy', 1.0, 'NONE', '', 'market'
        )
        
        # 驗證交易記錄
        balance = self.strategy.get_coin_balance()
        self.assertEqual(balance, 1.0)
    
    def test_execute_trade_sell(self):
        """測試執行賣出交易"""
        # 先執行一次買入
        self.mock_client.set_private_create_order.return_value = {'id': '12345'}
        self.mock_client.get_public_markets_summary.return_value = {
            'tickers': {
                'BTCtwd': {
                    'last': '500000'
                }
            }
        }
        
        self.strategy.execute_trade('buy', 1.0)
        
        # 執行賣出交易
        result = self.strategy.execute_trade('sell', 0.5)
        
        # 驗證交易執行
        self.assertTrue(result)
        
        # 驗證餘額
        balance = self.strategy.get_coin_balance()
        self.assertEqual(balance, 0.5)
    
    def test_check_and_trade(self):
        """測試檢查並執行交易策略"""
        # 模擬API響應
        self.mock_client.get_public_markets_summary.return_value = {
            'tickers': {
                'BTCtwd': {
                    'last': '500000'
                }
            }
        }
        self.mock_client.set_private_create_order.return_value = {'id': '12345'}
        
        # 測試需要買入的情況
        result = self.strategy.check_and_trade()
        self.assertIsNotNone(result)
        self.assertTrue('執行買入' in result)
        
        # 修改價格使餘額超過目標值
        self.mock_client.get_public_markets_summary.return_value = {
            'tickers': {
                'BTCtwd': {
                    'last': '1000000'
                }
            }
        }
        
        # 測試需要賣出的情況
        result = self.strategy.check_and_trade()
        self.assertIsNotNone(result)
        self.assertTrue('執行賣出' in result)
    
    def test_check_take_profit(self):
        """測試檢查停利條件"""
        # 模擬API響應
        self.mock_client.get_public_markets_summary.return_value = {
            'tickers': {
                'BTCtwd': {
                    'last': '1000000'
                }
            }
        }
        self.mock_client.set_private_create_order.return_value = {'id': '12345'}
        
        # 先執行買入
        self.strategy.execute_trade('buy', 1.0)
        
        # 測試達到停利條件
        result = self.strategy.check_take_profit()
        self.assertIsNotNone(result)
        self.assertTrue('達到停利條件' in result)
        
        # 驗證全部賣出
        balance = self.strategy.get_coin_balance()
        self.assertEqual(balance, 0.0)

if __name__ == '__main__':
    unittest.main()
