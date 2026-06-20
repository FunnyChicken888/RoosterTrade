"""模擬版 MAX 客戶端，提供與 ClientV3 相同的介面但回傳假資料。

用途：本機沒有真實 API 金鑰時，仍可啟動服務、看到 UI 與即時數據變化。
價格用「緩慢正弦波 + 小幅雜訊」模擬，所以每次刷新會有自然的小幅波動。
"""
import math
import time
import random


class MockClientV3:
    # 各市場的基準價（TWD）
    BASE_PRICES = {
        "btctwd": 3_250_000.0,
        "ethtwd": 115_000.0,
        "usdttwd": 32.3,
        "soltwd": 5_400.0,
    }

    def __init__(self, key=None, secret=None, timeout=30):
        self._t0 = time.time()
        # 模擬帳戶餘額
        self._balances = {
            "twd": 480_000.0,
            "btc": 0.085,
            "eth": 1.6,
            "usdt": 3_000.0,
        }

    # --- 內部工具 ---
    def _price(self, market):
        market = market.lower()
        base = self.BASE_PRICES.get(market, 1000.0)
        elapsed = time.time() - self._t0
        drift = math.sin(elapsed / 90.0) * 0.012      # 緩慢波段 ±1.2%
        noise = random.uniform(-0.0025, 0.0025)        # 即時雜訊 ±0.25%
        return round(base * (1 + drift + noise), 2)

    # --- 市場行情 API ---
    def get_market_summary(self):
        return [{"id": m, "base_unit": m[:-3], "quote_unit": "twd"} for m in self.BASE_PRICES]

    def get_trades(self, market, limit=1):
        price = self._price(market)
        return [{
            "id": int(time.time() * 1000),
            "price": str(price),
            "volume": "0.01",
            "market": market.lower(),
            "created_at": int(time.time()),
            "side": random.choice(["bid", "ask"]),
        }]

    # --- 帳戶 API ---
    def get_account_balance(self, wallet_type="spot"):
        return [
            {"currency": cur, "balance": str(bal), "locked": "0"}
            for cur, bal in self._balances.items()
        ]

    def get_my_trades(self, market, limit=50):
        return []

    # --- 交易 API（模擬下單，不會真的成交）---
    def create_order(self, market, side, volume, price=None, order_type="market", wallet_type="spot"):
        return {
            "id": int(time.time() * 1000),
            "market": market.lower(),
            "side": side,
            "ord_type": order_type,
            "volume": str(volume),
            "state": "done",
            "created_at": int(time.time()),
        }

    def cancel_order(self, order_id, wallet_type="spot"):
        return {"id": order_id, "state": "cancel"}

    def get_order(self, order_id, wallet_type="spot"):
        return {"id": order_id, "state": "done"}

    def get_orders(self, market, state="wait", wallet_type="spot"):
        return []
