"""DEMO 驗證建倉階段狀態機（target / chase 模式、改價、轉交易、開倉幣價）。

執行：  ../.venv/bin/python scripts/test_build_phase.py
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
from backend.strategies.strategy_manager import StrategyManager
from backend.utils.trading_record import TradingRecord
from backend.utils.paths import records_dir, strategies_dir

MARKET = "btctwd"
ok = True


def check(label, cond):
    global ok
    ok = ok and cond
    print(("  ✅" if cond else "  ❌") + f" {label}")


def cleanup(name):
    for d in (records_dir(), strategies_dir()):
        for p in glob.glob(os.path.join(d, f"*{name}*")):
            os.remove(p)


def mgr_for(name, client, build_mode="target", target_open_price=0):
    cfg = TradingStrategyConfig(
        strategy_name=name, investment_amount=35000.0, max_position=10000.0,
        take_profit=9e9, auto_trade_percent=2.0, coin_type="BTC",
        daily_trade_limit=99, build_mode=build_mode, target_open_price=target_open_price,
    )
    return MakerOrderManager(client, cfg, TradingRecord(name), notifier=None), cfg


def test_target():
    name = "__build_target__"; cleanup(name)
    client = MockClientV3(); client.set_price(MARKET, 2_000_000.0)
    mgr, cfg = mgr_for(name, client, "target", 1_980_000.0)

    print("[target] 步驟1：建倉中，掛固定目標價買單(未成交)")
    mgr.sync()
    check("phase=building", mgr.phase == "building")
    buys = [o for o in mgr.tracked.values() if o["side"] == "buy"]
    check("掛 1 張買單", len(buys) == 1)
    check("掛價=目標開倉價 1,980,000", abs(buys[0]["price"] - 1_980_000) < 1)
    check("尚未成交", mgr.trading_record.get_current_balance() == 0)

    print("[target] 步驟2：改價 → 買單重掛到新價")
    cfg.target_open_price = 1_970_000.0
    mgr.sync()
    buys = [o for o in mgr.tracked.values() if o["side"] == "buy"]
    check("買單掛價更新為 1,970,000", abs(buys[0]["price"] - 1_970_000) < 1)

    print("[target] 步驟3：價格觸及 → 全數建倉 → 轉交易階段")
    client.set_price(MARKET, 1_970_000.0)
    mgr.sync()
    check("phase=trading", mgr.phase == "trading")
    check("開倉均價≈1,970,000", abs(mgr.open_price - 1_970_000) < 100)
    check("建倉後市值≈35000", abs(mgr.trading_record.get_current_balance() * 1_970_000 - 35000) < 5)
    sides = {o["side"] for o in mgr.tracked.values()}
    check("交易階段掛出買+賣雙邊單", sides == {"buy", "sell"})
    cleanup(name)


def test_chase():
    name = "__build_chase__"; cleanup(name)
    client = MockClientV3(); client.set_price(MARKET, 2_000_000.0)
    client.set_spread_ticks(3)                       # bid=1999997, ask=2000003, tick=1
    mgr, cfg = mgr_for(name, client, "chase")

    print("[chase] 步驟1：掛在買一+1tick，維持 maker")
    mgr.sync()
    buys = [o for o in mgr.tracked.values() if o["side"] == "buy"]
    check("掛 1 張買單", len(buys) == 1)
    check("掛價=買一+1tick=1,999,998", abs(buys[0]["price"] - 1_999_998) < 0.5)

    print("[chase] 步驟2：價格下移觸及掛價 → 成交 → 轉交易")
    client.set_price(MARKET, 1_999_998.0)
    mgr.sync()
    check("phase=trading", mgr.phase == "trading")
    check("開倉均價≈1,999,998", abs(mgr.open_price - 1_999_998) < 100)

    print("[chase] 步驟3：買一+1tick 會變 taker 時改用買一價")
    c2 = MockClientV3(); c2.set_price(MARKET, 2_000_000.0); c2.set_spread_ticks(0)  # bid=ask=2000000
    m2, _ = mgr_for("__build_chase2__", c2, "chase")
    p = m2._compute_build_price(2_000_000.0)
    check("掛價=買一(2,000,000)而非買一+1tick", abs(p - 2_000_000) < 0.5)
    cleanup(name); cleanup("__build_chase2__")


def test_manager_exposes_open_price():
    name = "__build_mgr__"; cleanup(name)
    client = MockClientV3(); client.set_price(MARKET, 2_000_000.0)
    mgr = StrategyManager(client)
    cfg = TradingStrategyConfig(
        strategy_name=name, investment_amount=35000.0, max_position=10000.0,
        take_profit=9e9, auto_trade_percent=2.0, coin_type="BTC",
        daily_trade_limit=99, build_mode="target", target_open_price=1_960_000.0, is_active=True,
    )
    mgr.create_strategy(cfg)

    print("[manager] 建倉中 → API 顯示 phase=building")
    mgr.execute_all_strategies()
    st = [s for s in mgr.get_all_strategies() if s["config"]["strategy_name"] == name][0]
    check("get_all_strategies 有 open_price 欄位", "open_price" in st)
    check("建倉中 phase=building", st["phase"] == "building")

    print("[manager] 觸發建倉完成 → API 顯示 open_price")
    client.set_price(MARKET, 1_960_000.0)
    mgr.execute_all_strategies()
    st = [s for s in mgr.get_all_strategies() if s["config"]["strategy_name"] == name][0]
    check("phase 轉 trading", st["phase"] == "trading")
    check("open_price≈1,960,000", abs(st["open_price"] - 1_960_000) < 100)
    mgr.delete_strategy(name); cleanup(name)


if __name__ == "__main__":
    test_target()
    test_chase()
    test_manager_exposes_open_price()
    print("\n全部通過 ✅" if ok else "\n有測試未通過 ❌")
    sys.exit(0 if ok else 1)
