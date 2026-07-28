"""套利風控狀態快照（給網頁儀表板用，只讀公開行情、只示警、絕不下單）。

維護每個部位的短時價格滾動視窗（與 CLI 監控 monitor.py 同義），每次呼叫
get_snapshot() 重新拉公開行情、更新視窗，再用 risk_engine 算出各指標
（距離強平 %、資金費率年化、急拉幅度）與示警等級，供前端輪詢顯示。

設定來源：config/arb_monitor.json（與 scripts/run_arb_monitor.py 同一份）。
"""
import os
import json
import time
import logging
from collections import deque

from ..arb_monitor import feeds, risk_engine
from ..utils.paths import config_dir

logger = logging.getLogger("arb_status")

_buffers = {}          # key -> deque[(ts, mark)]，跨輪詢保留以偵測急拉
_RANK = {"OK": 0, "INFO": 1, "WARN": 2, "CRIT": 3, "ERR": 4}


def _config_file():
    return os.path.join(config_dir(), "arb_monitor.json")


def load_config():
    with open(_config_file(), "r", encoding="utf-8") as f:
        return json.load(f)


def _key(pos):
    return f"{pos.get('exchange')}:{pos.get('symbol')}:{pos.get('side')}"


def _window_extremes(key, ts, mark, window_sec):
    buf = _buffers.setdefault(key, deque())
    buf.append((ts, mark))
    while buf and ts - buf[0][0] > window_sec:
        buf.popleft()
    prices = [p for _, p in buf]
    return min(prices), max(prices)


def _worst(a, b):
    return a if _RANK.get(a, 0) >= _RANK.get(b, 0) else b


def get_snapshot():
    """回傳 {generated_at, window_min, worst_level, positions:[...]}。"""
    conf = load_config()
    positions = conf.get("positions") or []
    thresholds = conf.get("thresholds") or {}
    window_min = conf.get("window_min", 15)
    window_sec = window_min * 60
    ts = time.time()

    rows = []
    worst = "OK"
    for pos in positions:
        key = _key(pos)
        side = pos.get("side", "short")
        row = {
            "label": pos.get("label") or pos.get("symbol") or key,
            "exchange": pos.get("exchange"), "symbol": pos.get("symbol"),
            "side": side, "liq_price": pos.get("liq_price") or 0,
        }
        try:
            m = feeds.get_market(pos["exchange"], pos["symbol"])
        except Exception as e:
            logger.warning(f"{key} 取行情失敗：{e}")
            row.update({"level": "ERR", "error": str(e)})
            rows.append(row)
            worst = _worst(worst, "ERR")
            continue

        low, high = _window_extremes(key, ts, m["mark"], window_sec)
        market = {
            "mark": m["mark"], "funding_rate": m["funding_rate"],
            "funding_interval_hours": m["funding_interval_hours"],
            "recent_low": low, "recent_high": high,
        }
        alerts = risk_engine.evaluate(pos, market, thresholds)

        apr = risk_engine.funding_apr(float(m["funding_rate"]), m["funding_interval_hours"])
        recv = apr if side == "short" else -apr      # 你實收的年化（負=你付）
        buf_pct = risk_engine.liq_buffer_pct(side, m["mark"], pos.get("liq_price"))
        move = risk_engine.adverse_move_pct(side, m["mark"], low, high)

        level = "OK"
        for a in alerts:
            level = _worst(level, a["level"])

        row.update({
            "mark": round(m["mark"], 4),
            "funding_apr": round(recv, 2),
            "funding_interval_hours": m["funding_interval_hours"],
            "liq_buffer_pct": None if buf_pct is None else round(buf_pct, 2),
            "adverse_move_pct": round(move, 2),
            "level": level,
            "alerts": [{"level": a["level"], "code": a["code"], "msg": a["msg"]} for a in alerts],
        })
        rows.append(row)
        worst = _worst(worst, level)

    return {
        "generated_at": ts,
        "window_min": window_min,
        "worst_level": worst,
        "positions": rows,
    }
