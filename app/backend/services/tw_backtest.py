"""台股「定值再平衡」策略回測引擎（純函式，含台股費稅模型）。

沿用加密貨幣版的再平衡邏輯：維持持倉市值在目標 V 附近，偏差超過 band 就把
市值拉回 V（逢跌補、逢漲賣）。差異在於台股的真實成本：

  - 手續費 0.1425% × 折扣，每筆有低消（預設 NT$20），買賣都收。
  - 證券交易稅：只在「賣出」收，一般股 0.3%、ETF 0.1%、現股當沖 0.15%。
  - 成交單位為整數股（零股）。台股無 maker/taker，故以收盤觸發、收盤價成交建模。

損益定義（與 app 一致並延伸）：
  淨投資 = Σ買入金額 − Σ賣出金額（不含費稅）
  損益   = 期末持倉市值 − 淨投資 − 累積手續費 − 累積證交稅
"""
import math

# 法定費率基準
BASE_FEE_RATE = 0.001425
TAX_RATES = {"common": 0.003, "etf": 0.001, "daytrade": 0.0015}


def make_costs(fee_discount=0.6, fee_min=20.0, security_type="common"):
    """組裝成本參數。fee_discount: 手續費折扣（6 折=0.6）。"""
    return {
        "fee_rate": BASE_FEE_RATE * fee_discount,
        "fee_min": float(fee_min),
        "tax_rate": TAX_RATES.get(security_type, 0.003),
        "security_type": security_type,
    }


def _fee(amount, costs):
    if amount <= 0:
        return 0.0
    return max(amount * costs["fee_rate"], costs["fee_min"])


def run_backtest(prices, investment_amount, max_position, auto_trade_percent,
                 costs, take_profit=float("inf")):
    """對單一 band 跑回測。

    prices: [{date, open, high, low, close}]（依日期遞增）
    回傳 dict：trades、損益、費稅、ROI、買進持有基準、價格序列（供畫圖）。
    """
    V = float(investment_amount)
    band = float(auto_trade_percent)
    max_add = float(max_position)
    cap = float("inf") if max_add <= 0 else V + max_add
    closes = [(p["date"], float(p["close"])) for p in prices]

    shares = 0                 # 整數股
    net_inv = 0.0              # 淨投資（不含費稅）
    total_fee = 0.0
    total_tax = 0.0
    peak_inv = 0.0
    trades = []
    stopped = False

    def do_trade(date, side, px, qty):
        nonlocal shares, net_inv, total_fee, total_tax, peak_inv
        qty = int(qty)
        if qty <= 0:
            return
        amount = qty * px
        fee = _fee(amount, costs)
        tax = amount * costs["tax_rate"] if side == "sell" else 0.0
        if side == "buy":
            shares += qty
            net_inv += amount
        else:
            shares -= qty
            net_inv -= amount
        total_fee += fee
        total_tax += tax
        peak_inv = max(peak_inv, net_inv)
        trades.append({
            "date": date, "side": side, "price": round(px, 2),
            "shares": qty, "amount": round(amount, 2),
            "fee": round(fee, 2), "tax": round(tax, 2),
        })

    for i, (date, px) in enumerate(closes):
        if stopped:
            break
        value = shares * px

        # 停利：總市值達標則全數賣出並停止
        if shares > 0 and value >= take_profit:
            do_trade(date, "sell", px, shares)
            stopped = True
            continue

        if shares == 0:
            # 首次建倉：買到市值≈V
            do_trade(date, "buy", px, round(V / px))
            continue

        deviation = abs(value - V) / V * 100.0
        if deviation <= band:
            continue

        target = round(V / px)        # 讓市值回到 V 的目標股數
        if value < V:                 # 逢跌補
            if net_inv >= cap:        # 達加碼上限不再買（僅擋下一筆,故峰值可能溢出一個 slice,與實盤一致）
                continue
            do_trade(date, "buy", px, target - shares)
        else:                         # 逢漲賣
            do_trade(date, "sell", px, shares - target)

    last_px = closes[-1][1]
    final_value = shares * last_px
    profit = final_value - net_inv - total_fee - total_tax
    roi = profit / peak_inv * 100 if peak_inv > 0 else 0.0

    # 買進持有基準：首日以 V 建倉、抱到底（mark-to-market，不賣，故無證交稅）
    first_px = closes[0][1]
    bh_shares = round(V / first_px)
    bh_cost = bh_shares * first_px + _fee(bh_shares * first_px, costs)
    bh_final = bh_shares * last_px
    bh_profit = bh_final - bh_cost
    bh_roi = bh_profit / bh_cost * 100 if bh_cost > 0 else 0.0

    return {
        "band": band,
        "trades": trades,
        "n_trades": len(trades),
        "total_fee": round(total_fee, 2),
        "total_tax": round(total_tax, 2),
        "net_invested": round(net_inv, 2),
        "peak_invested": round(peak_inv, 2),
        "final_shares": shares,
        "final_value": round(final_value, 2),
        "profit": round(profit, 2),
        "roi": round(roi, 2),
        "buy_hold_profit": round(bh_profit, 2),
        "buy_hold_roi": round(bh_roi, 2),
        "series": [{"date": d, "close": c} for d, c in closes],
    }


def run_sweep(prices, investment_amount, max_position, bands, costs,
              take_profit=float("inf")):
    """對多個 band 跑回測，回傳結果清單（series 只附在第一個以省頻寬）。"""
    results = []
    for idx, band in enumerate(bands):
        res = run_backtest(prices, investment_amount, max_position, band, costs,
                           take_profit)
        if idx > 0:
            res.pop("series", None)
        # 各 band 的 trades 量可能大，掃描時只留摘要與第一個的明細
        if idx > 0:
            res["trades"] = []
        results.append(res)
    return results
