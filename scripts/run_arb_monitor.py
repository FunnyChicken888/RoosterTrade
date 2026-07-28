"""資金費率套利風控監控器 — CLI 執行迴圈（只示警，絕不下單）。

讀 config/arb_monitor.json（部位 + 門檻 + 輪詢秒數），每 poll_seconds 跑一輪
ArbMonitor.run_cycle()。預設只印 console（安全 dry-run）；確認門檻合理後，加
--telegram 才會真的推播（需 config/config.json 內已填 telegram_bot_token / chat_id）。

執行（在 repo 根目錄）：
  ../.venv/bin/python scripts/run_arb_monitor.py            # console dry-run，持續輪詢
  ../.venv/bin/python scripts/run_arb_monitor.py --once     # 只跑一輪就結束
  ../.venv/bin/python scripts/run_arb_monitor.py --telegram # 門檻調準後，開 Telegram 推播
"""
import os
import sys
import json
import time
import argparse
import logging

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from backend.arb_monitor.monitor import ArbMonitor, make_telegram_notify
from backend.utils.paths import config_dir, config_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("run_arb_monitor")


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_notify(use_telegram):
    """回傳 notify(msg, level)。--telegram 且金鑰齊全才實發，否則一律 console。"""
    def console_notify(msg, level):
        icon = {"INFO": "ℹ️", "WARN": "⚠️", "CRIT": "🚨"}.get(level, "")
        print(f"{icon} [{level}] {msg}", flush=True)

    if not use_telegram:
        return console_notify

    cfg = {}
    try:
        cfg = _load_json(config_path())
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"讀 config.json 失敗，退回 console：{e}")
        return console_notify

    token, chat = cfg.get("telegram_bot_token"), cfg.get("telegram_chat_id")
    placeholder = {"", None, "your_telegram_bot_token", "your_telegram_chat_id"}
    if token in placeholder or chat in placeholder:
        logger.warning("Telegram 金鑰未設定（仍是範本值），退回 console。")
        return console_notify

    from backend.utils.notification import TelegramNotifier
    notifier = TelegramNotifier(token, chat)
    logger.info("Telegram 推播已啟用。")
    return make_telegram_notify(notifier)


def run(args):
    cfg_file = args.config or os.path.join(config_dir(), "arb_monitor.json")
    try:
        conf = _load_json(cfg_file)
    except FileNotFoundError:
        logger.error(f"找不到設定檔：{cfg_file}\n請依範本建立（見 docs/arb_monitor_plan.md §4）。")
        return 1
    except json.JSONDecodeError as e:
        logger.error(f"設定檔格式錯誤：{e}")
        return 1

    positions = conf.get("positions") or []
    if not positions:
        logger.error("設定檔的 positions 是空的，無可監控部位。")
        return 1

    poll = args.poll or conf.get("poll_seconds", 30)
    monitor = ArbMonitor(
        positions,
        thresholds=conf.get("thresholds"),
        notify=build_notify(args.telegram),
        window_min=conf.get("window_min", 15),
        cooldown_min=conf.get("cooldown_min", 30),
    )

    mode = "Telegram" if args.telegram else "console dry-run"
    logger.info(f"監控啟動：{len(positions)} 個部位，每 {poll}s 一輪，模式={mode}。只示警，絕不下單。")

    while True:
        try:
            alerts = monitor.run_cycle()
            if not alerts:
                logger.info("本輪無示警（部位皆在門檻內）。")
        except Exception as e:
            logger.warning(f"本輪發生例外，略過：{e}")
        if args.once:
            return 0
        try:
            time.sleep(poll)
        except KeyboardInterrupt:
            logger.info("收到中斷，結束監控。")
            return 0


def main():
    p = argparse.ArgumentParser(description="資金費率套利風控監控器（只示警，不下單）")
    p.add_argument("--config", help="設定檔路徑（預設 config/arb_monitor.json）")
    p.add_argument("--once", action="store_true", help="只跑一輪就結束")
    p.add_argument("--telegram", action="store_true", help="實發 Telegram（預設只印 console）")
    p.add_argument("--poll", type=int, help="覆寫輪詢秒數")
    args = p.parse_args()
    try:
        sys.exit(run(args))
    except KeyboardInterrupt:
        logger.info("收到中斷，結束監控。")
        sys.exit(0)


if __name__ == "__main__":
    main()
