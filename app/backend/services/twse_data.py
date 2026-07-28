"""抓取台灣證交所（TWSE）真實每日行情。

資料源：證交所官方 STOCK_DAY 端點（免金鑰、單月一次）
  https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=YYYYMMDD&stockNo=2330

回傳乾淨的每日 OHLC，日期已由民國年轉為西元 ISO。已完成的月份做檔案快取，
當月一律重抓（資料每日更新）。僅涵蓋上市股票；上櫃(TPEx)需另接。
"""
import os
import json
import time
import logging
import datetime

import requests

from ..utils.paths import records_dir

logger = logging.getLogger("twse_data")

_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
_HEADERS = {"User-Agent": "Mozilla/5.0 (RoosterTrade backtest)"}
_FETCH_DELAY = 0.3   # 對 TWSE 友善，避免被限流


def _roc_to_iso(s):
    """民國年日期 '115/06/01' -> '2026-06-01'。"""
    y, m, d = s.strip().split("/")
    return f"{int(y) + 1911:04d}-{int(m):02d}-{int(d):02d}"


def _num(s):
    """'2,355.00' -> 2355.0；'--' 或空字串 -> None。"""
    s = (s or "").strip().replace(",", "")
    if s in ("", "--", "---", "X0.00"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _cache_path(stock_no):
    return os.path.join(records_dir(), f"twse_cache_{stock_no}.json")


def _load_cache(stock_no):
    try:
        with open(_cache_path(stock_no), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(stock_no, cache):
    with open(_cache_path(stock_no), "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def _fetch_month(stock_no, year, month):
    """抓單月每日 OHLC，回傳 [{date, open, high, low, close}]。"""
    date_param = f"{year:04d}{month:02d}01"
    r = requests.get(
        _URL,
        params={"response": "json", "date": date_param, "stockNo": stock_no},
        headers=_HEADERS, timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("stat") != "OK":
        # 多半是該股無資料或代號錯誤
        raise ValueError(f"TWSE 回應非 OK（{stock_no} {year}/{month}）：{data.get('stat')}")

    rows = []
    for rec in data.get("data") or []:
        try:
            o, h, l, c = _num(rec[3]), _num(rec[4]), _num(rec[5]), _num(rec[6])
        except IndexError:
            continue
        if None in (o, h, l, c):
            continue  # 跳過停牌/無成交日
        rows.append({
            "date": _roc_to_iso(rec[0]),
            "open": o, "high": h, "low": l, "close": c,
        })
    return rows


def fetch_daily_ohlc(stock_no, months=12):
    """抓近 months 個月的每日 OHLC（含當月）。已完成月份走快取，當月重抓。

    回傳依日期排序的 [{date, open, high, low, close}]。
    """
    stock_no = str(stock_no).strip()
    today = datetime.date.today()
    cache = _load_cache(stock_no)
    cur_key = f"{today.year:04d}{today.month:02d}"

    # 產生需要的 (year, month) 清單
    needed = []
    y, m = today.year, today.month
    for _ in range(max(1, months)):
        needed.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    needed.reverse()

    all_rows = []
    fetched_any = False
    for (yy, mm) in needed:
        key = f"{yy:04d}{mm:02d}"
        if key != cur_key and key in cache:
            all_rows.extend(cache[key])
            continue
        try:
            if fetched_any:
                time.sleep(_FETCH_DELAY)
            rows = _fetch_month(stock_no, yy, mm)
            fetched_any = True
        except Exception as e:
            logger.warning(f"抓 {stock_no} {key} 失敗，略過：{e}")
            continue
        if key != cur_key:
            cache[key] = rows  # 只快取已完成的月份
        all_rows.extend(rows)

    if fetched_any:
        _save_cache(stock_no, cache)

    # 去重（以日期）並排序
    by_date = {row["date"]: row for row in all_rows}
    result = [by_date[d] for d in sorted(by_date)]
    if not result:
        raise ValueError(f"找不到 {stock_no} 的行情資料，請確認是否為有效的上市股票代號")
    return result
