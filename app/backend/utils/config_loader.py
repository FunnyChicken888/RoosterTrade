"""統一讀取設定檔，並把不同命名風格的金鑰正規化。

之前的問題：
- app.py 讀的是 `max_api_key` / `max_secret_key`，但 config_example.json 寫的是
  `CLIENT_API_KEY` / `CLIENT_SECRET_KEY`，導致金鑰永遠讀不到。
- auto_trade_strategy.py 讀 `telegram_bot_token`（小寫），config_example.json 卻是
  `TELEGRAM_BOT_TOKEN`（大寫），Telegram 通知永遠初始化失敗。

這裡用別名表把這些寫法都接受，回傳統一的小寫鍵。
"""
import os
import json
import logging

from .paths import config_path

logger = logging.getLogger("config_loader")

# 正規化鍵 -> 可接受的別名（依序比對，取第一個有值者）
_ALIASES = {
    "telegram_bot_token": ["telegram_bot_token", "TELEGRAM_BOT_TOKEN"],
    "telegram_chat_id": ["telegram_chat_id", "TELEGRAM_CHAT_ID"],
    "max_api_key": ["max_api_key", "MAX_API_KEY", "CLIENT_API_KEY", "client_api_key"],
    "max_secret_key": ["max_secret_key", "MAX_SECRET_KEY", "CLIENT_SECRET_KEY", "client_secret_key"],
}


def _truthy(v):
    return str(v).lower() in ("1", "true", "yes", "on")


def load_config():
    """回傳正規化後的設定 dict，並附帶 `demo_mode` 旗標。"""
    path = config_path()
    raw = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        logger.warning(f"找不到設定檔，將以空設定執行: {path}")
    except json.JSONDecodeError as e:
        logger.error(f"設定檔格式錯誤: {path} - {e}")

    cfg = {}
    for canon, names in _ALIASES.items():
        for n in names:
            if raw.get(n) not in (None, ""):
                cfg[canon] = raw[n]
                break
        cfg.setdefault(canon, "")

    # demo 模式：設定檔 demo_mode=true 或環境變數 ROOSTER_DEMO=1，
    # 或完全沒有 API 金鑰時，自動使用模擬資料（方便本機看 UI）。
    env_demo = _truthy(os.getenv("ROOSTER_DEMO", ""))
    cfg_demo = bool(raw.get("demo_mode", False))
    no_keys = not (cfg["max_api_key"] and cfg["max_secret_key"])
    cfg["demo_mode"] = env_demo or cfg_demo or no_keys
    return cfg
