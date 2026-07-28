"""監控 orchestration：拉行情 → 算風險 → 示警（只示警，絕不下單）。

- 為每個部位維護一個短時價格滾動視窗，用來偵測「急拉/尬空」。
- 示警去重：同一 (部位, 風險碼) 在冷卻時間內不重複轟炸，但嚴重度升級會再發。
- notify 是可插拔的 callable(msg, level)；接 Telegram 或先印到 console。
"""
import time
import logging
from collections import deque

from . import feeds
from . import risk_engine

logger = logging.getLogger("arb_monitor")


class ArbMonitor:
    def __init__(self, positions, thresholds=None, notify=None,
                 window_min=15, cooldown_min=30, clock=time.time):
        self.positions = positions
        self.thresholds = thresholds or {}
        self.notify = notify or (lambda msg, level: print(f"[{level}] {msg}"))
        self.window_sec = window_min * 60
        self.cooldown_sec = cooldown_min * 60
        self._clock = clock
        self._buffers = {}        # key -> deque[(ts, mark)]
        self._last_alert = {}     # (key, code) -> (ts, level)

    @staticmethod
    def _key(pos):
        return f"{pos.get('exchange')}:{pos.get('symbol')}:{pos.get('side')}"

    def _window_extremes(self, key, ts, mark):
        buf = self._buffers.setdefault(key, deque())
        buf.append((ts, mark))
        while buf and ts - buf[0][0] > self.window_sec:
            buf.popleft()
        lows = [p for _, p in buf]
        return min(lows), max(lows)

    def _should_send(self, key, code, level, ts):
        prev = self._last_alert.get((key, code))
        rank = {"INFO": 0, "WARN": 1, "CRIT": 2}
        if prev is None:
            return True
        prev_ts, prev_level = prev
        if rank[level] > rank[prev_level]:    # 嚴重度升級 → 立即再發
            return True
        return ts - prev_ts >= self.cooldown_sec

    def run_cycle(self):
        """跑一輪：回傳本輪所有 alert（含被冷卻擋下的，方便顯示狀態）。"""
        ts = self._clock()
        all_alerts = []
        for pos in self.positions:
            key = self._key(pos)
            try:
                m = feeds.get_market(pos["exchange"], pos["symbol"])
            except Exception as e:
                logger.warning(f"{key} 取行情失敗：{e}")
                continue
            low, high = self._window_extremes(key, ts, m["mark"])
            market = {
                "mark": m["mark"],
                "funding_rate": m["funding_rate"],
                "funding_interval_hours": m["funding_interval_hours"],
                "recent_low": low, "recent_high": high,
            }
            alerts = risk_engine.evaluate(pos, market, self.thresholds)
            for a in alerts:
                a["key"] = key
                all_alerts.append(a)
                if self._should_send(key, a["code"], a["level"], ts):
                    self._last_alert[(key, a["code"])] = (ts, a["level"])
                    try:
                        self.notify(a["msg"], a["level"])
                    except Exception as e:
                        logger.warning(f"示警送出失敗：{e}")
        return all_alerts


def make_telegram_notify(notifier, strategy_name="套利風控"):
    """把既有 TelegramNotifier 包成 notify(msg, level)。"""
    def _notify(msg, level):
        icon = {"INFO": "ℹ️", "WARN": "⚠️", "CRIT": "🚨"}.get(level, "")
        notifier.send_trade_result(strategy_name, level != "CRIT", f"{icon} [{level}] {msg}")
    return _notify
