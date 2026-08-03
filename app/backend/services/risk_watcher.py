"""定期巡檢各交易所合約部位，觸發風控示警時推播 Telegram；
必要時對派網做「站內 MAIN → TRADE」自動補保證金。

設計上的安全邊界：
- 只讀取部位，唯一的寫入動作是派網站內劃轉（不可能提領到站外，派網 API 也沒有提領端點）。
- 自動補保證金預設關閉，必須在設定檔明確開啟。
- 每次劃轉有單筆上限、每日總量上限與冷卻時間，且一定會發 Telegram 通知。
- 同一個示警不重複轟炸：同部位同代碼在冷卻時間內只推一次。
"""
import logging
import threading
import time
from datetime import datetime, date

logger = logging.getLogger("risk_watcher")

LEVEL_ICON = {"CRIT": "🚨", "WARN": "⚠️", "INFO": "ℹ️"}


class RiskWatcher:
    def __init__(self, collect_positions, notifier=None, pionex_transfer=None, config=None):
        """
        collect_positions: 無參數 callable，回傳正規化後的部位清單（含 alerts）。
        notifier:          TelegramNotifier；None 表示不推播。
        pionex_transfer:   PionexTransferClient；None 表示不啟用自動補保證金。
        """
        self.collect_positions = collect_positions
        self.notifier = notifier
        self.pionex = pionex_transfer
        cfg = config or {}

        self.interval = max(int(cfg.get("risk_watch_interval", 300) or 300), 60)
        self.alert_cooldown = max(int(cfg.get("risk_alert_cooldown", 3600) or 3600), 300)

        # 自動補保證金（預設關閉）
        self.topup_enabled = bool(cfg.get("pionex_auto_topup", False))
        self.topup_buffer_pct = float(cfg.get("pionex_topup_buffer_pct", 8.0) or 8.0)
        self.topup_amount = float(cfg.get("pionex_topup_amount", 200) or 200)
        self.topup_daily_cap = float(cfg.get("pionex_topup_daily_cap", 1000) or 1000)
        self.topup_cooldown = max(int(cfg.get("pionex_topup_cooldown", 1800) or 1800), 300)

        self._sent = {}            # (exchange, symbol, code) -> 上次推播時間
        self._last_topup_at = 0.0
        self._topup_day = None
        self._topup_today = 0.0
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()

    # ── 示警推播 ──────────────────────────────────────────────
    def _should_send(self, key, now):
        last = self._sent.get(key)
        if last and now - last < self.alert_cooldown:
            return False
        self._sent[key] = now
        return True

    def _notify_alerts(self, positions, now):
        lines = []
        for p in positions:
            for a in p.get("alerts", []):
                key = (p["exchange"], p["symbol"], a["code"])
                if self._should_send(key, now):
                    lines.append("{} <b>{}</b> {}".format(
                        LEVEL_ICON.get(a["level"], ""), a["level"], a["msg"]))
        if lines and self.notifier:
            self.notifier.send_text("🐓 <b>RoosterTrade 風控示警</b>\n\n" + "\n\n".join(lines))
            logger.info("已推播 %d 則風控示警", len(lines))
        return len(lines)

    # ── 派網站內自動補保證金 ──────────────────────────────────
    @staticmethod
    def _liq_buffer_pct(position):
        """距離強平的緩衝 %；沒有強平價則回 None。"""
        mark = position.get("mark_price") or 0
        liq = position.get("liquidation_price") or 0
        if not mark or not liq:
            return None
        if position.get("side") == "short":
            return (liq - mark) / mark * 100.0
        return (mark - liq) / mark * 100.0

    def _reset_daily_cap_if_needed(self):
        today = date.today()
        if self._topup_day != today:
            self._topup_day = today
            self._topup_today = 0.0

    def _maybe_topup(self, positions, now):
        if not (self.topup_enabled and self.pionex):
            return
        risky = [
            p for p in positions
            if p.get("exchange") == "pionex"
            and (self._liq_buffer_pct(p) is not None)
            and self._liq_buffer_pct(p) <= self.topup_buffer_pct
        ]
        if not risky:
            return
        if now - self._last_topup_at < self.topup_cooldown:
            logger.info("派網補保證金仍在冷卻中，略過")
            return

        self._reset_daily_cap_if_needed()
        remaining = self.topup_daily_cap - self._topup_today
        if remaining <= 0:
            logger.warning("派網補保證金已達每日上限 %.2f，略過", self.topup_daily_cap)
            if self.notifier:
                self.notifier.send_text(
                    "⛔️ 派網保證金偏低，但今日自動劃轉已達上限 "
                    "{:.2f} USDT，請手動處理。".format(self.topup_daily_cap))
            return

        amount = min(self.topup_amount, remaining)
        try:
            main = self.pionex.get_main_balance("USDT")
            free = float(main.get("free") or 0)
        except Exception as error:
            logger.exception("讀取派網主帳戶餘額失敗")
            if self.notifier:
                self.notifier.send_text("⚠️ 派網保證金偏低，但讀取主帳戶餘額失敗：{}".format(error))
            return

        if free < amount:
            msg = ("⛔️ 派網保證金偏低，但主帳戶(MAIN)可用僅 {:.2f} USDT，不足以劃轉 {:.2f}。\n"
                   "你的閒置資金多半在 Pionex Card／理財產品中，需要先手動贖回到主帳戶。"
                   ).format(free, amount)
            logger.warning(msg)
            if self.notifier and self._should_send(("pionex", "MAIN", "insufficient"), now):
                self.notifier.send_text(msg)
            return

        try:
            self.pionex.transfer_main_to_trade(
                amount, "USDT",
                client_id="rt-{}".format(int(now)),
                comment="auto margin topup",
            )
            self._last_topup_at = now
            self._topup_today += amount
            symbols = "、".join(p["symbol"] for p in risky)
            text = ("✅ <b>派網自動補保證金</b>\n\n"
                    "已從主帳戶劃轉 <b>{:.2f} USDT</b> 到合約帳戶。\n"
                    "觸發部位：{}\n今日累計劃轉：{:.2f} / {:.2f} USDT"
                    ).format(amount, symbols, self._topup_today, self.topup_daily_cap)
            logger.info("派網自動劃轉 %.2f USDT 成功", amount)
            if self.notifier:
                self.notifier.send_text(text)
        except Exception as error:
            logger.exception("派網自動劃轉失敗")
            if self.notifier:
                self.notifier.send_text("❌ 派網自動補保證金失敗：{}".format(error))

    # ── 主迴圈 ────────────────────────────────────────────────
    def check_once(self):
        with self._lock:
            try:
                positions = self.collect_positions() or []
            except Exception:
                logger.exception("巡檢部位失敗")
                return 0
            now = time.time()
            count = self._notify_alerts(positions, now)
            self._maybe_topup(positions, now)
            return count

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def loop():
            while not self._stop.is_set():
                started = time.time()
                self.check_once()
                self._stop.wait(max(0, self.interval - (time.time() - started)))

        self._thread = threading.Thread(target=loop, name="risk-watcher", daemon=True)
        self._thread.start()
        logger.info(
            "風控巡檢已啟動，間隔 %s 秒；派網自動補保證金：%s",
            self.interval, "開啟" if self.topup_enabled else "關閉",
        )

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._thread = None
