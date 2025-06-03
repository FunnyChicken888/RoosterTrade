import unittest
import os
import json
from datetime import datetime
from ..utils.trading_record import TradingRecord

class TestTradingRecord(unittest.TestCase):
    def setUp(self):
        self.strategy_name = "test_strategy"
        self.trading_record = TradingRecord(self.strategy_name)
        self.test_file = f"trading_records_{self.strategy_name}.json"
    
    def tearDown(self):
        # 清理測試文件
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
    
    def test_init_and_load(self):
        """測試初始化和加載功能"""
        # 新建的TradingRecord應該有空的交易記錄
        self.assertEqual(len(self.trading_record.trade_records), 0)
        
        # 創建一些測試數據並保存
        self.trading_record.add_trade_record(
            datetime.now().isoformat(),
            100.0,
            1.0,
            'buy'
        )
        
        # 創建新的實例來測試加載
        new_record = TradingRecord(self.strategy_name)
        self.assertEqual(len(new_record.trade_records), 1)
    
    def test_add_trade_record(self):
        """測試添加交易記錄"""
        # 添加買入記錄
        self.trading_record.add_trade_record(
            datetime.now().isoformat(),
            100.0,
            1.0,
            'buy'
        )
        
        # 驗證記錄是否正確保存
        self.assertEqual(len(self.trading_record.trade_records), 1)
        record = self.trading_record.trade_records[0]
        self.assertEqual(record['strategy_name'], self.strategy_name)
        self.assertEqual(record['price'], 100.0)
        self.assertEqual(record['volume'], 1.0)
        self.assertEqual(record['action'], 'buy')
        
        # 驗證文件是否正確保存
        with open(self.test_file, 'r') as f:
            data = json.load(f)
            self.assertEqual(len(data['trade_records']), 1)
    
    def test_get_current_balance(self):
        """測試餘額計算"""
        # 添加一系列交易記錄
        self.trading_record.add_trade_record(
            datetime.now().isoformat(),
            100.0,
            1.0,
            'buy'
        )
        self.trading_record.add_trade_record(
            datetime.now().isoformat(),
            110.0,
            0.5,
            'sell'
        )
        self.trading_record.add_trade_record(
            datetime.now().isoformat(),
            120.0,
            0.3,
            'buy'
        )
        
        # 驗證餘額計算
        # 1.0 - 0.5 + 0.3 = 0.8
        expected_balance = 0.8
        self.assertAlmostEqual(self.trading_record.get_current_balance(), expected_balance)
    
    def test_get_current_market_value(self):
        """測試市值計算"""
        # 添加交易記錄
        self.trading_record.add_trade_record(
            datetime.now().isoformat(),
            100.0,
            1.0,
            'buy'
        )
        self.trading_record.add_trade_record(
            datetime.now().isoformat(),
            110.0,
            0.5,
            'sell'
        )
        
        # 測試市值計算
        # 當前餘額: 0.5, 當前價格: 120.0
        current_price = 120.0
        expected_value = 0.5 * current_price  # 60.0
        self.assertEqual(self.trading_record.get_current_market_value(current_price), expected_value)
    
    def test_edge_cases(self):
        """測試邊界情況"""
        # 測試空記錄的餘額
        self.assertEqual(self.trading_record.get_current_balance(), 0.0)
        
        # 測試空記錄的市值
        self.assertEqual(self.trading_record.get_current_market_value(100.0), 0.0)
        
        # 測試全部賣出後的餘額
        self.trading_record.add_trade_record(
            datetime.now().isoformat(),
            100.0,
            1.0,
            'buy'
        )
        self.trading_record.add_trade_record(
            datetime.now().isoformat(),
            110.0,
            1.0,
            'sell'
        )
        self.assertEqual(self.trading_record.get_current_balance(), 0.0)

if __name__ == '__main__':
    unittest.main()
