"""交易所公開行情（免金鑰）：標記價、資金費率、24h 區間。

幣安 USDⓈ-M：fapi.binance.com（premiumIndex / ticker 24hr / openInterest）
BingX 永續：open-api.bingx.com（premiumIndex / ticker）

回傳正規化 dict：{exchange, symbol, mark, funding_rate, funding_interval_hours,
                 high_24h, low_24h, last, change_24h_pct}
"""
import logging
import requests

logger = logging.getLogger("arb_feeds")
_HEADERS = {"User-Agent": "Mozilla/5.0 (RoosterTrade arb-monitor)"}
_TIMEOUT = 12


def _get(url, params=None):
    r = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def binance_perp(symbol):
    pi = _get("https://fapi.binance.com/fapi/v1/premiumIndex", {"symbol": symbol})
    out = {
        "exchange": "binance", "symbol": symbol,
        "mark": float(pi["markPrice"]),
        "funding_rate": float(pi["lastFundingRate"]),
        "funding_interval_hours": 8,        # 幣安多為 8h
        "high_24h": None, "low_24h": None, "last": None, "change_24h_pct": None,
    }
    try:
        t = _get("https://fapi.binance.com/fapi/v1/ticker/24hr", {"symbol": symbol})
        out["high_24h"] = float(t["highPrice"]); out["low_24h"] = float(t["lowPrice"])
        out["last"] = float(t["lastPrice"]); out["change_24h_pct"] = float(t["priceChangePercent"])
    except Exception as e:
        logger.warning(f"binance 24hr {symbol} 失敗：{e}")
    return out


def bingx_perp(symbol):
    pi = _get("https://open-api.bingx.com/openApi/swap/v2/quote/premiumIndex", {"symbol": symbol})
    d = pi.get("data", pi)
    out = {
        "exchange": "bingx", "symbol": symbol,
        "mark": float(d["markPrice"]),
        "funding_rate": float(d["lastFundingRate"]),
        "funding_interval_hours": int(d.get("fundingIntervalHours", 8) or 8),
        "high_24h": None, "low_24h": None, "last": None, "change_24h_pct": None,
    }
    try:
        t = _get("https://open-api.bingx.com/openApi/swap/v2/quote/ticker", {"symbol": symbol})
        td = t.get("data", t)
        out["high_24h"] = float(td["highPrice"]); out["low_24h"] = float(td["lowPrice"])
        out["last"] = float(td["lastPrice"]); out["change_24h_pct"] = float(td.get("priceChangePercent", 0))
    except Exception as e:
        logger.warning(f"bingx ticker {symbol} 失敗：{e}")
    return out


def get_market(exchange, symbol):
    ex = (exchange or "").lower()
    if ex == "binance":
        return binance_perp(symbol)
    if ex == "bingx":
        return bingx_perp(symbol)
    raise ValueError(f"未支援的交易所：{exchange}")
