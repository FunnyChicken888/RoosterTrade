"""模擬版 MAX 客戶端，提供與 ClientV3 相同的介面但回傳假資料。

用途：本機沒有真實 API 金鑰時，仍可啟動服務、看到 UI 與即時數據變化。

此版為「有狀態的限價模擬交易所」：
- 市價單立即以當前價成交。
- 限價單會掛著（state='wait'），直到模擬價格穿過掛價才成交
  （買單 current<=price 成交；賣單 current>=price 成交）。
- 成交會更新帳戶餘額，並反映在 get_account_balance。
- get_order / get_orders 會先「結算」一次再回傳，讓掛單循環可被端到端測試。

價格用「緩慢正弦波 + 小幅雜訊」模擬；測試時可用 set_price() 直接指定。
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
        self._orders = {}          # id -> order dict
        self._next_id = 1
        self._forced_price = {}    # market -> 指定價（測試用），None 表示用正弦波
        self._partial_ratio = {}   # id -> 首次只成交的比例（測試部分成交用）
        self._spread_ticks = 3     # 模擬買一/賣一相對中價各偏離幾個 tick

    # --- 內部工具 ---
    def _price(self, market):
        market = market.lower()
        if self._forced_price.get(market) is not None:
            return self._forced_price[market]
        base = self.BASE_PRICES.get(market, 1000.0)
        elapsed = time.time() - self._t0
        drift = math.sin(elapsed / 90.0) * 0.012      # 緩慢波段 ±1.2%
        noise = random.uniform(-0.0025, 0.0025)        # 即時雜訊 ±0.25%
        return round(base * (1 + drift + noise), 2)

    def _base_unit(self, market):
        return market.lower()[:-3]

    def _settle(self):
        """結算所有 wait 單：價格穿過掛價即成交（可部分），更新餘額。"""
        for o in self._orders.values():
            if o["state"] != "wait":
                continue
            market = o["market"]
            cur = self._price(market)
            price = float(o["price"])
            hit = (o["side"] == "buy" and cur <= price) or \
                  (o["side"] == "sell" and cur >= price)
            if not hit:
                continue

            remaining = float(o["remaining_volume"])
            # 測試用：首次只成交一部分，剩下留待下次結算
            ratio = self._partial_ratio.pop(o["id"], 1.0)
            fill = remaining * ratio
            if fill <= 0:
                continue

            base = self._base_unit(market)
            if o["side"] == "buy":
                self._balances[base] = self._balances.get(base, 0.0) + fill
                self._balances["twd"] = self._balances.get("twd", 0.0) - fill * price
            else:
                self._balances[base] = self._balances.get(base, 0.0) - fill
                self._balances["twd"] = self._balances.get("twd", 0.0) + fill * price

            executed = float(o["executed_volume"]) + fill
            o["executed_volume"] = executed
            o["remaining_volume"] = max(0.0, float(o["volume"]) - executed)
            o["avg_price"] = price
            if o["remaining_volume"] <= 1e-12:
                o["state"] = "done"

    # --- 測試輔助（真實 API 沒有，僅供 DEMO/測試驅動）---
    def set_price(self, market, price):
        """直接指定某市場現價；傳 None 還原為正弦波。"""
        self._forced_price[market.lower()] = price

    def set_partial_next(self, order_id, ratio):
        """讓某張單下次結算只成交 ratio 比例（測試部分成交）。"""
        self._partial_ratio[order_id] = ratio

    def set_spread_ticks(self, ticks):
        """設定模擬買一/賣一的價差寬度（單位：tick），測試追買一用。"""
        self._spread_ticks = ticks

    # --- 委託簿 / tick ---
    def tick_size(self, market):
        """依價位量級回傳最小跳動單位（模擬用，非真實 MAX 精度）。"""
        p = self._price(market)
        if p >= 1000:
            return 1.0
        if p >= 100:
            return 0.5
        if p >= 10:
            return 0.05
        return 0.01

    def get_depth(self, market, limit=1):
        """回傳模擬委託簿最佳買賣價（買一/賣一各偏離中價 _spread_ticks 個 tick）。"""
        market = market.lower()
        p = self._price(market)
        t = self.tick_size(market)
        half = t * self._spread_ticks
        best_bid = round((p - half) / t) * t
        best_ask = round((p + half) / t) * t
        return {"bids": [[str(best_bid), "1.0"]], "asks": [[str(best_ask), "1.0"]]}

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
            {"currency": cur, "balance": str(round(bal, 10)), "locked": "0"}
            for cur, bal in self._balances.items()
        ]

    def get_my_trades(self, market, limit=50):
        return []

    # --- 交易 API ---
    def create_order(self, market, side, volume, price=None, order_type="market", wallet_type="spot"):
        market = market.lower()
        side = side.lower()
        volume = float(volume)
        oid = self._next_id
        self._next_id += 1
        order = {
            "id": oid,
            "market": market,
            "side": side,
            "ord_type": order_type.lower(),
            "price": str(price) if price is not None else None,
            "avg_price": "0",
            "volume": str(volume),
            "executed_volume": 0.0,
            "remaining_volume": volume,
            "state": "wait",
            "created_at": int(time.time()),
        }
        self._orders[oid] = order

        if order_type.lower() == "market":
            # 市價單立即以當前價成交
            cur = self._price(market)
            base = self._base_unit(market)
            if side == "buy":
                self._balances[base] = self._balances.get(base, 0.0) + volume
                self._balances["twd"] = self._balances.get("twd", 0.0) - volume * cur
            else:
                self._balances[base] = self._balances.get(base, 0.0) - volume
                self._balances["twd"] = self._balances.get("twd", 0.0) + volume * cur
            order["state"] = "done"
            order["executed_volume"] = volume
            order["remaining_volume"] = 0.0
            order["avg_price"] = str(cur)
        return dict(order)

    def cancel_order(self, order_id, wallet_type="spot"):
        o = self._orders.get(int(order_id))
        if o and o["state"] == "wait":
            o["state"] = "cancel"
        return dict(o) if o else {"id": order_id, "state": "cancel"}

    def get_order(self, order_id, wallet_type="spot"):
        self._settle()
        o = self._orders.get(int(order_id))
        return dict(o) if o else {"id": order_id, "state": "cancel"}

    def get_orders(self, market, state="wait", wallet_type="spot"):
        self._settle()
        return [
            dict(o) for o in self._orders.values()
            if o["market"] == market.lower() and o["state"] == state
        ]
