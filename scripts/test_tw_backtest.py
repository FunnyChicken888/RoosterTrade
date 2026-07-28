"""tw_backtest 引擎單元測試（合成序列，驗證費稅與邏輯正確）。"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))

from backend.services.tw_backtest import run_backtest, make_costs

ok = True
def check(label, cond):
    global ok; ok = ok and cond
    print(("  ✅" if cond else "  ❌") + f" {label}")

def series(closes):
    return [{"date": f"2026-01-{i+1:02d}", "open": c, "high": c, "low": c, "close": c}
            for i, c in enumerate(closes)]

costs = make_costs(fee_discount=0.6, fee_min=20.0, security_type="common")

print("情境A：純上漲 → 逢漲賣出,證交稅只在賣出計")
A = run_backtest(series([100, 100, 130, 130]), 35000, 10000, 5, costs)
sells = [t for t in A["trades"] if t["side"] == "sell"]
buys = [t for t in A["trades"] if t["side"] == "buy"]
check("有買有賣", len(buys) >= 1 and len(sells) >= 1)
check("買單不收證交稅", all(t["tax"] == 0 for t in buys))
check("賣單有收證交稅", all(t["tax"] > 0 for t in sells))
check("證交稅率=賣出額×0.3%", abs(sells[0]["tax"] - sells[0]["amount"] * 0.003) < 0.01)
check("上漲盤策略獲利為正", A["profit"] > 0)

print("情境B：純下跌 → 一路加碼,淨投資封頂在 V+max_position=45000")
B = run_backtest(series([100, 95, 90, 85, 80, 75, 70, 65, 60]), 35000, 10000, 3, costs)
# 加碼上限僅擋下一筆,故峰值可溢出一個 rebalance slice(與實盤一致),容差設一個 slice
check(f"淨投資封頂≈45000,溢出不超過一個 slice(峰值 {B['peak_invested']:,.0f})",
      B["peak_invested"] <= 45000 + 35000 * 0.12)
check("下跌盤虧損為負", B["profit"] < 0)
check("有交易發生", B["n_trades"] >= 2)

print("情境C：盤整 → 來回再平衡,費稅累積")
C = run_backtest(series([100, 103, 100, 103, 100, 103, 100]), 35000, 10000, 2, costs)
check("手續費累積為正", C["total_fee"] > 0)
check("總損益 = 市值−淨投資−費−稅", abs(
    C["profit"] - (C["final_value"] - C["net_invested"] - C["total_fee"] - C["total_tax"])) < 0.01)

print("情境D：買進持有基準合理")
D = run_backtest(series([100, 110]), 35000, 10000, 5, costs)
check("上漲時買進持有報酬為正", D["buy_hold_roi"] > 0)
check("低消生效:小額單手續費=NT$20", any(t["fee"] == 20.0 for t in D["trades"]) or D["trades"][0]["fee"] >= 20.0)

print("情境E：max_position=0 → 不設加碼上限")
E = run_backtest(series([100, 80, 60, 40, 20]), 35000, 0, 3, costs)
check("不設上限時下跌會持續加碼，峰值投入超過 V", E["peak_invested"] > 35000)

print("情境F：series 與 trades 結構供前端畫圖")
check("有 series 價格序列", len(D["series"]) == 2 and "close" in D["series"][0])
check("trades 含日期/方向/股數", all(k in D["trades"][0] for k in ("date", "side", "shares")))

print("\n全部通過 ✅" if ok else "\n有測試未通過 ❌")
sys.exit(0 if ok else 1)
