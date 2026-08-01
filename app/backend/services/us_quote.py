"""抓取美股／ETF 即時報價（供避險監控的手動多腿自動更新現價用）。

資料源：Yahoo Finance chart 端點（免金鑰）
  https://query1.finance.yahoo.com/v8/finance/chart/SLV?interval=1d&range=1d

像 SLV 這種公開交易的 ETF 不需要券商 API（Firstrade 也沒有），直接抓市場行情即可。
報價做記憶體快取，避免頁面輪詢時對 Yahoo 發出過多請求。
"""
import logging
import threading
import time

import requests

logger = logging.getLogger("us_quote")

_HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")
_PATH = "/v8/finance/chart/{symbol}?interval=1d&range=1d"
_HEADERS = {"User-Agent": "Mozilla/5.0 (RoosterTrade hedge-monitor)"}
_TIMEOUT = 10
_CACHE_TTL = 60          # 秒；報價快取時間

_cache = {}              # symbol -> (fetched_at, quote dict)
_lock = threading.Lock()


def _fetch(symbol):
    """向 Yahoo 取單一標的報價；query1 失敗時改用 query2。"""
    last_error = None
    for host in _HOSTS:
        url = host + _PATH.format(symbol=symbol)
        try:
            response = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            chart = payload.get("chart") or {}
            if chart.get("error"):
                raise RuntimeError(chart["error"].get("description") or "Yahoo 回傳錯誤")
            results = chart.get("result") or []
            if not results:
                raise RuntimeError("找不到報價資料")
            meta = results[0].get("meta") or {}
            price = meta.get("regularMarketPrice")
            if price is None:
                raise RuntimeError("報價缺少成交價")
            previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
            change_pct = None
            if previous_close:
                change_pct = (float(price) / float(previous_close) - 1.0) * 100.0
            return {
                "symbol": meta.get("symbol", symbol),
                "price": float(price),
                "currency": meta.get("currency", "USD"),
                "previous_close": float(previous_close) if previous_close else None,
                "change_pct": change_pct,
                "market_time": meta.get("regularMarketTime"),
                "market_state": meta.get("marketState"),
                "exchange": meta.get("fullExchangeName"),
                "source": "Yahoo Finance",
            }
        except Exception as error:
            last_error = error
            logger.warning("取得 %s 報價失敗（%s）：%s", symbol, host, error)
    raise RuntimeError("無法取得 {} 報價：{}".format(symbol, last_error))


def get_quote(symbol, max_age=_CACHE_TTL):
    """回傳快取或最新報價。symbol 例如 'SLV'、'GLD'、'AAPL'。"""
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise ValueError("未指定報價代號")
    now = time.time()
    with _lock:
        cached = _cache.get(symbol)
        if cached and now - cached[0] < max_age:
            return dict(cached[1], cached=True)
    quote = _fetch(symbol)
    with _lock:
        _cache[symbol] = (now, quote)
    return dict(quote, cached=False)
