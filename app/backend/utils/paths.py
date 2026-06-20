"""集中管理專案路徑，避免各模組各自用相對層級推導路徑而產生不一致。

之前的問題：
- app.py / telegram_bot.py 寫死了 Docker 容器內的絕對路徑 `/app/config/config.json`，
  本機執行時永遠找不到設定檔。
- strategy_manager 推導 records 路徑時多接了一層 `app/`，導致路徑錯誤。

此模組把所有資料目錄統一以 `app/` 作為基準，並同時相容 Docker 與本機。
"""
import os

# 此檔案位於 app/backend/utils/paths.py，往上三層即 app/
APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO_ROOT = os.path.dirname(APP_DIR)


def _first_existing(paths, default):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return default


def config_dir():
    """設定檔目錄。優先環境變數，其次 app/config，最後 repo/config。"""
    env = os.getenv("CONFIG_DIR")
    candidates = [env, os.path.join(APP_DIR, "config"), os.path.join(REPO_ROOT, "config")]
    return _first_existing(candidates, os.path.join(APP_DIR, "config"))


def config_path():
    """config.json 完整路徑（相容舊的 CONFIG_PATH 環境變數）。"""
    env = os.getenv("CONFIG_PATH")
    if env:
        return env
    return os.path.join(config_dir(), "config.json")


def strategies_dir():
    d = os.path.join(config_dir(), "strategies")
    os.makedirs(d, exist_ok=True)
    return d


def records_dir():
    d = os.path.join(APP_DIR, "records")
    os.makedirs(d, exist_ok=True)
    return d
