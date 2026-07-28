"""台股上市公司清單（代號 ↔ 公司簡稱），供回測頁自動完成與依公司名搜尋。

資料源：證交所 OpenAPI 上市公司基本資料（免金鑰）
  https://openapi.twse.com.tw/v1/opendata/t187ap03_L

記憶體 + 檔案快取，TTL 一天；抓取失敗時退回舊快取，避免讓回測頁掛掉。
僅涵蓋上市；上櫃(TPEx)需另接。
"""
import os
import json
import time
import logging

import requests

from ..utils.paths import records_dir

logger = logging.getLogger("twse_stocks")

_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"      # 上市公司
_ETF_URL = "https://openapi.twse.com.tw/v1/ETFReport/ETFRank"   # 熱門 ETF（前 20）
_HEADERS = {"User-Agent": "Mozilla/5.0 (RoosterTrade)"}
_TTL = 86400  # 一天
_mem = {"ts": 0, "list": None, "by_code": {}}


def _cache_path():
    return os.path.join(records_dir(), "twse_stock_list.json")


def _load_file():
    try:
        with open(_cache_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_file(payload):
    with open(_cache_path(), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def _fetch():
    r = requests.get(_URL, headers=_HEADERS, timeout=20)
    r.raise_for_status()
    by_code = {}
    for row in r.json():
        code = (row.get("公司代號") or "").strip()
        name = (row.get("公司簡稱") or "").strip()
        if code and name:
            by_code[code] = name

    # 併入熱門 ETF（t187ap03_L 只含上市公司、不含 ETF）。抓失敗就略過。
    try:
        er = requests.get(_ETF_URL, headers=_HEADERS, timeout=15)
        er.raise_for_status()
        for row in er.json():
            code = (row.get("ETFsSecurityCode") or "").strip()
            name = (row.get("ETFsName") or "").strip()
            if code and name:
                by_code.setdefault(code, name)
    except Exception as e:
        logger.warning(f"抓熱門 ETF 清單失敗，略過：{e}")

    out = [{"code": c, "name": n} for c, n in by_code.items()]
    out.sort(key=lambda x: x["code"])
    return out


def _set_mem(ts, lst):
    _mem["ts"] = ts
    _mem["list"] = lst
    _mem["by_code"] = {s["code"]: s["name"] for s in lst}


def get_stock_list():
    """回傳 [{code, name}]。記憶體→檔案→重抓；抓取失敗退回舊快取。"""
    now = time.time()
    if _mem["list"] is not None and now - _mem["ts"] < _TTL:
        return _mem["list"]

    cached = _load_file()
    if cached and now - cached.get("ts", 0) < _TTL:
        _set_mem(cached["ts"], cached["list"])
        return cached["list"]

    try:
        lst = _fetch()
        _save_file({"ts": now, "list": lst})
        _set_mem(now, lst)
        return lst
    except Exception as e:
        logger.warning(f"抓上市公司清單失敗：{e}")
        if cached:                      # 退回舊快取（即使過期）
            _set_mem(cached.get("ts", 0), cached["list"])
            return cached["list"]
        return _mem["list"] or []


def get_name(code):
    """代號 → 公司簡稱；查不到回空字串。"""
    code = str(code).strip()
    get_stock_list()                    # 確保快取已載入
    return _mem["by_code"].get(code, "")
