"""長期收集各交易所永續合約的資金費率，特別關注 RWA（現實資產代幣化）合約。

三家都支援「一次呼叫抓全部」，所以每輪只要 3 個 HTTP 請求：
  幣安  GET /fapi/v1/premiumIndex            （855 檔）
  BingX GET /openApi/swap/v2/quote/premiumIndex（961 檔，且提供 fundingIntervalHours）
  派網  GET /api/v1/market/indexes            （597 檔，nextFundingRate）

資料以「每個結算期一列」去重（exchange, symbol, next_funding_time），
所以長期下來是乾淨的時間序列，不會因為輪詢頻率而灌水。
"""
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone

import requests

logger = logging.getLogger("funding_rates")

_HEADERS = {"User-Agent": "Mozilla/5.0 (RoosterTrade funding-collector)"}
_TIMEOUT = 25

# RWA（現實資產代幣化）辨識規則
#   BingX：NCSK*=個股/ETF、NCCO*=大宗商品、NCFX*=外匯
#   派網 ：AAPLX_USDT_PERP 這類 *X_ 結尾，加上貴金屬
_RWA_PATTERNS = (
    re.compile(r"^NC(SK|CO|FX)", re.I),                      # BingX
    re.compile(r"^[A-Z]{2,6}X_USDT_PERP$"),                   # 派網個股/ETF
    re.compile(r"^(XAU|XAG|XAUT)[_-]", re.I),                 # 貴金屬
    re.compile(r"^XAUT", re.I),                               # 幣安 XAUTUSDT
)

# 你特別關注的標的 → 各所對應合約（查詢時可用 group 一次比較同一標的）
RWA_GROUPS = {
    "SLV/白銀": [
        ("bingx", "NCSKSLV2USD-USDT"),
        ("bingx", "NCCOXAG2USD-USDT"),
        ("pionex", "SLVX_USDT_PERP"),
        ("pionex", "XAG_USDT_PERP"),
    ],
    "GOLD/黃金": [
        ("bingx", "NCCOGOLD2USD-USDT"),
        ("pionex", "XAU_USDT_PERP"),
        ("pionex", "XAUT_USDT_PERP"),
        ("binance", "XAUTUSDT"),
    ],
    "台積電": [
        ("bingx", "NCSKTSMU2USD-USDT"),
        ("pionex", "TSMX_USDT_PERP"),
    ],
    "AAPL": [("bingx", "NCSKAAPL2USD-USDT"), ("pionex", "AAPLX_USDT_PERP")],
    "NVDA": [("bingx", "NCSKNVDA2USD-USDT"), ("pionex", "NVDAX_USDT_PERP")],
    "TSLA": [("bingx", "NCSKTSLA2USD-USDT"), ("pionex", "TSLAX_USDT_PERP")],
    "MSTR": [("bingx", "NCSKMSTR2USD-USDT"), ("pionex", "MSTRX_USDT_PERP")],
    "QQQ": [("bingx", "NCSKQQQ2USD-USDT"), ("pionex", "QQQX_USDT_PERP")],
}


def is_rwa(symbol):
    return any(p.search(symbol or "") for p in _RWA_PATTERNS)


def _f(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def annualized_pct(rate, interval_hours):
    """單期資金費率 → 年化 %（正值代表多單付給空單，也就是做空方收）。"""
    if rate is None:
        return None
    interval_hours = interval_hours or 8
    return rate * (24.0 / interval_hours) * 365.0 * 100.0


# ── 各交易所抓取（皆為公開端點，不需金鑰）────────────────────────
def fetch_binance():
    rows = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex",
                        headers=_HEADERS, timeout=_TIMEOUT).json()
    out = []
    for r in rows if isinstance(rows, list) else []:
        out.append({
            "exchange": "binance",
            "symbol": r.get("symbol"),
            "funding_rate": _f(r.get("lastFundingRate")),
            "funding_interval_hours": 8,      # 幣安多數為 8h（部分 4h，此處不逐檔查）
            "next_funding_time": _f(r.get("nextFundingTime")),
            "mark_price": _f(r.get("markPrice")),
            "index_price": _f(r.get("indexPrice")),
        })
    return out


def fetch_bingx():
    payload = requests.get("https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex",
                           headers=_HEADERS, timeout=_TIMEOUT).json()
    rows = payload.get("data") or []
    out = []
    for r in rows if isinstance(rows, list) else []:
        out.append({
            "exchange": "bingx",
            "symbol": r.get("symbol"),
            "funding_rate": _f(r.get("lastFundingRate")),
            "funding_interval_hours": int(_f(r.get("fundingIntervalHours"), 8) or 8),
            "next_funding_time": _f(r.get("nextFundingTime")),
            "mark_price": _f(r.get("markPrice")),
            "index_price": _f(r.get("indexPrice")),
        })
    return out


def fetch_pionex():
    payload = requests.get("https://api.pionex.com/api/v1/market/indexes",
                           headers=_HEADERS, timeout=_TIMEOUT).json()
    data = payload.get("data") or {}
    rows = data.get("indexes") if isinstance(data, dict) else data
    if rows is None and isinstance(data, dict) and data:
        rows = data[list(data.keys())[0]]
    out = []
    for r in rows or []:
        out.append({
            "exchange": "pionex",
            "symbol": r.get("symbol"),
            "funding_rate": _f(r.get("nextFundingRate")),
            "funding_interval_hours": 8,
            "next_funding_time": _f(r.get("nextFundingTime")),
            "mark_price": _f(r.get("markPrice")),
            "index_price": _f(r.get("indexPrice")),
        })
    return out


_FETCHERS = {"binance": fetch_binance, "bingx": fetch_bingx, "pionex": fetch_pionex}


class FundingRateStore:
    def __init__(self, database_path):
        self.database_path = database_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(database_path), exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS funding_rates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exchange TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    funding_rate REAL,
                    funding_interval_hours INTEGER,
                    apr REAL,
                    next_funding_time INTEGER,
                    mark_price REAL,
                    index_price REAL,
                    is_rwa INTEGER NOT NULL DEFAULT 0,
                    collected_at TEXT NOT NULL,
                    UNIQUE(exchange, symbol, next_funding_time)
                );
                CREATE INDEX IF NOT EXISTS idx_funding_symbol_time
                    ON funding_rates(exchange, symbol, next_funding_time DESC);
                CREATE INDEX IF NOT EXISTS idx_funding_rwa
                    ON funding_rates(is_rwa, next_funding_time DESC);
            """)

    def save(self, rows):
        """以 (exchange, symbol, next_funding_time) 去重；同結算期以最新估值覆蓋。"""
        now = datetime.now(timezone.utc).isoformat()
        payload = []
        for r in rows:
            if not r.get("symbol") or r.get("funding_rate") is None:
                continue
            payload.append((
                r["exchange"], r["symbol"], r["funding_rate"],
                r.get("funding_interval_hours") or 8,
                annualized_pct(r["funding_rate"], r.get("funding_interval_hours")),
                int(r["next_funding_time"]) if r.get("next_funding_time") else None,
                r.get("mark_price"), r.get("index_price"),
                1 if is_rwa(r["symbol"]) else 0, now,
            ))
        if not payload:
            return 0
        with self._lock, self._connect() as connection:
            connection.executemany("""
                INSERT INTO funding_rates
                    (exchange, symbol, funding_rate, funding_interval_hours, apr,
                     next_funding_time, mark_price, index_price, is_rwa, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exchange, symbol, next_funding_time) DO UPDATE SET
                    funding_rate = excluded.funding_rate,
                    apr = excluded.apr,
                    mark_price = excluded.mark_price,
                    index_price = excluded.index_price,
                    collected_at = excluded.collected_at
            """, payload)
        return len(payload)

    def latest(self, rwa_only=False, exchange=None, limit=200, order="apr"):
        """各合約最新一筆資金費率，預設依年化排序。"""
        where, params = ["1=1"], []
        if rwa_only:
            where.append("is_rwa = 1")
        if exchange:
            where.append("exchange = ?")
            params.append(exchange)
        order_by = "ABS(f.apr) DESC" if order == "abs_apr" else "f.apr DESC"
        sql = """
            SELECT f.* FROM funding_rates f
            JOIN (
                SELECT exchange, symbol, MAX(next_funding_time) AS mt
                FROM funding_rates WHERE {} GROUP BY exchange, symbol
            ) m ON m.exchange = f.exchange AND m.symbol = f.symbol
               AND m.mt = f.next_funding_time
            ORDER BY {} LIMIT ?
        """.format(" AND ".join(where), order_by)
        with self._connect() as connection:
            return [dict(r) for r in connection.execute(sql, params + [int(limit)])]

    def history(self, exchange, symbol, limit=500):
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT * FROM funding_rates
                WHERE exchange = ? AND symbol = ?
                ORDER BY next_funding_time DESC LIMIT ?
            """, (exchange, symbol, int(limit)))
            return [dict(r) for r in rows]

    def stats(self, exchange, symbol, days=30):
        """指定期間的平均／最大／最小年化，用來評估這檔長期值不值得做。"""
        since = int((time.time() - days * 86400) * 1000)
        with self._connect() as connection:
            row = connection.execute("""
                SELECT COUNT(*) n, AVG(apr) avg_apr, MIN(apr) min_apr, MAX(apr) max_apr,
                       AVG(funding_rate) avg_rate
                FROM funding_rates
                WHERE exchange = ? AND symbol = ? AND next_funding_time >= ?
            """, (exchange, symbol, since)).fetchone()
        return dict(row) if row else {}

    def group_compare(self, days=30):
        """把同一標的在各交易所的年化並列，方便挑「在哪一家做空最划算」。"""
        result = {}
        for name, members in RWA_GROUPS.items():
            entries = []
            for exchange, symbol in members:
                latest = self.history(exchange, symbol, limit=1)
                if not latest:
                    continue
                entry = dict(latest[0])
                entry.update(self.stats(exchange, symbol, days) or {})
                entries.append(entry)
            if entries:
                result[name] = sorted(entries, key=lambda e: -(e.get("apr") or 0))
        return result

    def summary(self):
        with self._connect() as connection:
            row = connection.execute("""
                SELECT COUNT(*) rows, COUNT(DISTINCT exchange || symbol) symbols,
                       MIN(collected_at) first_at, MAX(collected_at) last_at
                FROM funding_rates
            """).fetchone()
        return dict(row) if row else {}


class FundingCollector:
    def __init__(self, store, interval_seconds=1800):
        self.store = store
        self.interval = max(int(interval_seconds), 300)
        self._thread = None
        self._stop = threading.Event()

    def collect_once(self):
        total, errors = 0, []
        for name, fetch in _FETCHERS.items():
            try:
                rows = fetch()
                saved = self.store.save(rows)
                total += saved
                logger.info("資金費率收集 %s：%d 檔", name, saved)
            except Exception as error:
                logger.warning("資金費率收集 %s 失敗：%s", name, error)
                errors.append("{}：{}".format(name, error))
        return {"saved": total, "errors": errors}

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def loop():
            while not self._stop.is_set():
                started = time.time()
                try:
                    self.collect_once()
                except Exception:
                    logger.exception("資金費率收集迴圈異常")
                self._stop.wait(max(0, self.interval - (time.time() - started)))

        self._thread = threading.Thread(target=loop, name="funding-collector", daemon=True)
        self._thread.start()
        logger.info("資金費率收集器已啟動，間隔 %s 秒", self.interval)

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._thread = None
