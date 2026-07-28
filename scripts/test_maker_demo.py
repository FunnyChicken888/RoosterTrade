"""DEMO 端到端驗證 maker 掛單循環（不需金鑰、不碰真實交易所）。

用升級後的 MockClientV3（有狀態限價模擬），驅動 MakerOrderManager 走過：
  1. 首次建倉（掛 maker 買單 → 價格跌到掛價 → 成交建倉）
  2. 逢漲：賣單成交、買單重掛
  3. 逢跌：買單成交、加碼
  4. 部分成交：剩餘量留到下輪補成交
  5. 加碼上限：淨投資達上限後不再掛買單
  6. 重啟對帳：用新物件載入持久化的掛單 id，不重複下單
執行：  ../.venv/bin/python scripts/test_maker_demo.py
"""
import os
import sys
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")
sys.path.insert(0, APP)

from max.mock_client import MockClientV3
from backend.models.strategy_config import TradingStrategyConfig
from backend.strategies.maker_orders import MakerOrderManager
from backend.utils.trading_record import TradingRecord
from backend.utils.paths import records_dir

NAME = "__maker_test__"
MARKET = "btctwd"
PASS, FAIL = "  ✅", "  ❌"
ok = True


def check(label, cond):
    global ok
    ok = ok and cond
    print((PASS if cond else FAIL) + f" {label}")


def cleanup():
    for p in glob.glob(os.path.join(records_dir(), f"*{NAME}*")):
        os.remove(p)


def fresh_manager(client, config):
    tr = TradingRecord(NAME)
    return MakerOrderManager(client, config, tr, notifier=None), tr


def main():
    cleanup()
    client = MockClientV3()
    client.set_price(MARKET, 2_000_000.0)   # 固定基準價，方便推演
    config = TradingStrategyConfig(
        strategy_name=NAME, investment_amount=35000.0, max_position=10000.0,
        take_profit=10_000_000.0, auto_trade_percent=2.0, coin_type="BTC",
        daily_trade_limit=99,
    )
    mgr, tr = fresh_manager(client, config)

    print("步驟1：首次建倉 — 應掛一張 maker 買單(無成交)")
    mgr.sync()
    buys = [o for o in mgr.tracked.values() if o["side"] == "buy"]
    check("掛出 1 張買單", len(buys) == 1)
    check("尚無成交記錄", tr.get_current_balance() == 0)
    build_price = buys[0]["price"]            # 2,000,000*(1-0.02)=1,960,000

    print("步驟2：價格跌到買單掛價 → 建倉成交")
    client.set_price(MARKET, build_price)
    mgr.sync()
    bal = tr.get_current_balance()
    val = bal * build_price
    check("已建立持倉", bal > 0)
    check("建倉後市值≈投資額(35000)", abs(val - 35000) < 1)
    check("買進記錄寫入 1 筆", len(tr.trade_records) == 1)
    check("建倉後已掛出買+賣兩張單", len(mgr.tracked) == 2)

    print("步驟3：價格漲穿賣單掛價 → 賣出、市值回到目標")
    p_sell = [o["price"] for o in mgr.tracked.values() if o["side"] == "sell"][0]
    client.set_price(MARKET, p_sell)
    mgr.sync()
    check("新增一筆賣出記錄", len(tr.trade_records) == 2)
    check("最後一筆為 sell", tr.trade_records[-1]["action"] == "sell")
    val2 = tr.get_current_balance() * p_sell
    check("賣後市值拉回≈35000", abs(val2 - 35000) < 1)
    check("成交後又重掛兩張單", len(mgr.tracked) == 2)

    print("步驟4：部分成交 — 買單只先成交 60%,記一筆且不重複計")
    oid_buy, price_buy = [(oid, o["price"]) for oid, o in mgr.tracked.items()
                          if o["side"] == "buy"][0]
    vol_buy = mgr.tracked[oid_buy]["volume"]
    before = len(tr.trade_records)
    client.set_partial_next(int(oid_buy), 0.6)
    client.set_price(MARKET, price_buy)
    mgr.sync()                                  # 記到 60%,剩餘撤單重掛
    last = tr.trade_records[-1]
    check("部分成交記了一筆", len(tr.trade_records) == before + 1)
    check("記錄量為掛單量的 60%", abs(last["volume"] - vol_buy * 0.6) < vol_buy * 1e-6)
    check("該掛單已不在追蹤中(剩餘已撤)", oid_buy not in mgr.tracked)
    mgr.sync()                                   # 同價再跑一輪:重掛的新買單更低、賣單更高,皆不成交
    check("不重複計入同一張單的成交", len(tr.trade_records) == before + 1)

    print("步驟5：加碼上限 — 持續下跌,淨投資封頂在 V+max_position(允許單筆 slice 溢出)")
    one_slice = config.investment_amount * (config.auto_trade_percent / 100)  # ~700
    price = price_buy
    for _ in range(60):
        price *= 0.99                            # 一路下跌 1%/步
        client.set_price(MARKET, price)
        mgr.sync()
    net = tr.get_net_investment()
    has_buy = any(o["side"] == "buy" for o in mgr.tracked.values())
    cap = config.investment_amount + config.max_position
    check(f"淨投資封頂≈45000,溢出不超過一個 slice (實際 {net:,.0f})",
          net <= cap + one_slice * 1.5)
    check("達上限後不再掛買單", not has_buy)

    print("步驟6：每日次數上限 — 設為已達標，應撤掉所有掛單")
    config.daily_trade_limit = 0
    mgr.sync()
    check("掛單全數撤銷", len(mgr.tracked) == 0)

    print("步驟7：重啟對帳 — 新物件載入持久化 id,不重複下單")
    config.daily_trade_limit = 99
    mgr.sync()                                   # 先重新掛單並持久化
    n_open = len(mgr.tracked)
    mgr2, _ = fresh_manager(client, config)      # 模擬重啟
    check("重啟後載入既有掛單", len(mgr2.tracked) == n_open)
    mgr2.sync()
    check("重啟對帳後掛單數不爆增", len(mgr2.tracked) <= n_open + 1)

    print()
    print("全部通過 ✅" if ok else "有測試未通過 ❌")
    cleanup()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
