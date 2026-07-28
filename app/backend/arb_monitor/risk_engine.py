"""風控指標與示警判斷（純函式，不連網、不下單）。

監控三類風險（以你的「空腿」為主，但同時支援多腿）：
  1. 保證金緩衝 / 距離強平：標記價離強平價還有多少 %。
  2. 資金費率異常：翻成「你付費」或對手方過熱（異常高）。
  3. 價格急拉 / 尬空：短時間內價格往不利方向急衝。

evaluate() 回傳 [{level, code, msg}]；level ∈ {INFO, WARN, CRIT}。
"""

DEFAULT_THRESHOLDS = {
    "liq_buffer_warn": 8.0,     # 距離強平 ≤ 此 % → WARN
    "liq_buffer_crit": 4.0,     # 距離強平 ≤ 此 % → CRIT
    "funding_pay_apr": 5.0,     # 你「付」資金費年化 ≥ 此 % → WARN
    "funding_high_apr": 50.0,   # 對手方過熱（你收的年化）≥ 此 % → INFO 提醒尬空
    "squeeze_pct": 3.0,         # 不利方向急衝 ≥ 此 %（在視窗內）→ CRIT
}


def funding_apr(rate, interval_hours):
    """單次資金費率 → 年化 %（正=多單付給空單）。"""
    if not interval_hours:
        interval_hours = 8
    return rate * (24.0 / interval_hours) * 365.0 * 100.0


def liq_buffer_pct(side, mark, liq_price):
    """標記價距離強平價的緩衝 %（越小越危險；≤0 表示已觸及/穿越強平）。"""
    if not liq_price or mark <= 0:
        return None
    if side == "short":      # 空單強平價在標記價之上
        return (liq_price - mark) / mark * 100.0
    return (mark - liq_price) / mark * 100.0   # 多單強平價在下


def adverse_move_pct(side, mark, recent_low, recent_high):
    """往「不利方向」的急衝幅度 %。空單怕漲（從近期低點漲多少），多單怕跌。"""
    if side == "short":
        if not recent_low:
            return 0.0
        return (mark - recent_low) / recent_low * 100.0
    if not recent_high:
        return 0.0
    return (recent_high - mark) / recent_high * 100.0


def evaluate(position, market, cfg=None):
    """對單一部位產出示警清單。

    position: {label, side('short'/'long'), mark 來源, liq_price, ...}
    market:   {mark, funding_rate, funding_interval_hours, recent_low, recent_high}
    """
    c = dict(DEFAULT_THRESHOLDS)
    if cfg:
        c.update(cfg)
    side = position.get("side", "short")
    label = position.get("label", position.get("symbol", "?"))
    mark = float(market["mark"])
    alerts = []

    # 1. 保證金緩衝 / 距離強平
    buf = liq_buffer_pct(side, mark, position.get("liq_price"))
    if buf is not None:
        if buf <= 0:
            alerts.append({"level": "CRIT", "code": "liq",
                           "msg": f"{label}：已觸及強平價！標記 {mark:,.2f}"})
        elif buf <= c["liq_buffer_crit"]:
            alerts.append({"level": "CRIT", "code": "liq",
                           "msg": f"{label}：距離強平僅 {buf:.1f}%（標記 {mark:,.2f} / 強平 {position['liq_price']:,.2f}），請立即減倉或加保證金"})
        elif buf <= c["liq_buffer_warn"]:
            alerts.append({"level": "WARN", "code": "liq",
                           "msg": f"{label}：保證金緩衝收斂至 {buf:.1f}%，留意追繳"})

    # 2. 資金費率異常
    rate = market.get("funding_rate")
    if rate is not None:
        apr = funding_apr(float(rate), market.get("funding_interval_hours", 8))
        recv = apr if side == "short" else -apr   # 你實收的年化（負=你付）
        if recv < 0 and -recv >= c["funding_pay_apr"]:
            alerts.append({"level": "WARN", "code": "funding_pay",
                           "msg": f"{label}：資金費翻成你付費，年化 {recv:+.1f}%（{side} 不利）"})
        elif recv >= c["funding_high_apr"]:
            alerts.append({"level": "INFO", "code": "funding_high",
                           "msg": f"{label}：資金費異常高 +{recv:.0f}%/年，對手方過熱，慎防劇烈回歸/尬空"})

    # 3. 價格急拉 / 尬空
    move = adverse_move_pct(side, mark, market.get("recent_low"), market.get("recent_high"))
    if move >= c["squeeze_pct"]:
        direction = "急漲" if side == "short" else "急跌"
        alerts.append({"level": "CRIT", "code": "squeeze",
                       "msg": f"{label}：價格{direction} {move:.1f}%（標記 {mark:,.2f}），{side} 尬{'空' if side=='short' else '多'}風險，考慮減倉"})

    return alerts
