"""arb 風控引擎單元測試（純函式、不連網）。
執行：  ../.venv/bin/python scripts/test_arb_risk.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
from backend.arb_monitor import risk_engine as re

ok = True
def check(label, cond):
    global ok; ok = ok and cond
    print(("  ✅" if cond else "  ❌") + f" {label}")

def codes(alerts):
    return {a["code"] for a in alerts}
def level_of(alerts, code):
    return next((a["level"] for a in alerts if a["code"] == code), None)

POS = {"label": "幣安PAXG空", "side": "short", "liq_price": 4400.0}

print("1. 距離強平：安全 / 接近 / 危急")
a = re.evaluate(POS, {"mark": 4000, "funding_rate": 0.0001, "funding_interval_hours": 8,
                      "recent_low": 4000, "recent_high": 4000})
check("緩衝 10% 不示警 liq", "liq" not in codes(a))
a = re.evaluate(POS, {"mark": 4120, "funding_rate": 0.0001, "funding_interval_hours": 8,
                      "recent_low": 4120, "recent_high": 4120})   # 緩衝(4400-4120)/4120=6.8%
check("緩衝 6.8% → WARN", level_of(a, "liq") == "WARN")
a = re.evaluate(POS, {"mark": 4250, "funding_rate": 0.0001, "funding_interval_hours": 8,
                      "recent_low": 4250, "recent_high": 4250})   # 緩衝 3.5%
check("緩衝 3.5% → CRIT", level_of(a, "liq") == "CRIT")

print("2. 資金費率：翻負(你付) / 異常高")
# 空單：rate<0 → 你付費。rate=-0.0005, 8h → 年化 -0.0005*3*365*100 = -54.75% → 你付 54.75%
a = re.evaluate({"label":"x","side":"short"},
                {"mark":4000,"funding_rate":-0.0005,"funding_interval_hours":8,"recent_low":4000})
check("空單 funding 翻負 → WARN funding_pay", level_of(a, "funding_pay") == "WARN")
# 空單收很高：rate=+0.0005 → 年化 +54.75% → INFO 過熱
a = re.evaluate({"label":"x","side":"short"},
                {"mark":4000,"funding_rate":0.0005,"funding_interval_hours":8,"recent_low":4000})
check("空單 funding 異常高 → INFO funding_high", level_of(a, "funding_high") == "INFO")
# 正常小幅 → 不示警
a = re.evaluate({"label":"x","side":"short"},
                {"mark":4000,"funding_rate":0.00003,"funding_interval_hours":8,"recent_low":4000})
check("funding 正常 → 不示警", "funding_pay" not in codes(a) and "funding_high" not in codes(a))

print("3. 價格急拉 / 尬空（空單怕漲）")
a = re.evaluate({"label":"x","side":"short"},
                {"mark":4160,"funding_rate":0.0001,"funding_interval_hours":8,"recent_low":4000})  # +4%
check("自近期低點急漲 4% → CRIT squeeze", level_of(a, "squeeze") == "CRIT")
a = re.evaluate({"label":"x","side":"short"},
                {"mark":4040,"funding_rate":0.0001,"funding_interval_hours":8,"recent_low":4000})  # +1%
check("僅 +1% → 不示警 squeeze", "squeeze" not in codes(a))

print("4. 多單方向相反（怕跌、付費）")
LP = {"label":"多腿","side":"long","liq_price":3600.0}
a = re.evaluate(LP, {"mark":3720,"funding_rate":0.0005,"funding_interval_hours":8,"recent_high":3720})
check("多單緩衝 (3720-3600)/3720=3.2% → CRIT liq", level_of(a,"liq")=="CRIT")
a = re.evaluate({"label":"多","side":"long"},
                {"mark":3800,"funding_rate":0.0005,"funding_interval_hours":8,
                 "recent_high":4000})  # 跌 5%
check("多單急跌 5% → CRIT squeeze", level_of(a,"squeeze")=="CRIT")
check("多單 funding 正(你付) → WARN", level_of(a,"funding_pay")=="WARN")

print("\n全部通過 ✅" if ok else "\n有測試未通過 ❌")
sys.exit(0 if ok else 1)
