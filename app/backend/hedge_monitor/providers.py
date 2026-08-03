import hashlib
import hmac
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests


class MaxPublicClient:
    """Public MAX market data used to value USDT positions in TWD."""

    BASE_URL = "https://max-api.maicoin.com"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()

    def get_usdt_twd(self) -> Dict[str, Any]:
        response = self.session.get(
            self.BASE_URL + "/api/v2/tickers/usdttwd", timeout=self.timeout
        )
        response.raise_for_status()
        payload = response.json()
        ticker = payload.get("ticker", payload)
        last = ticker.get("last") or ticker.get("close")
        if last is None:
            raise RuntimeError("MAX usdttwd 行情缺少最新成交價")
        return {
            "rate": float(last),
            "bid": float(ticker["buy"]) if ticker.get("buy") is not None else None,
            "ask": float(ticker["sell"]) if ticker.get("sell") is not None else None,
            "timestamp": payload.get("at"),
            "market": "usdttwd",
            "source": "MAX",
        }


class BingXReadOnlyClient:
    BASE_URL = "https://open-api.bingx.com"

    def __init__(self, api_key: str = "", secret_key: str = "", timeout: int = 10):
        self.api_key = api_key or ""
        self.secret_key = secret_key or ""
        self.timeout = timeout
        self.session = requests.Session()

    @property
    def authenticated(self) -> bool:
        return bool(self.api_key and self.secret_key)

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None, signed=False):
        query = dict(params or {})
        headers = {}
        if signed:
            if not self.authenticated:
                raise RuntimeError("尚未設定 BingX 唯讀 API Key")
            query["timestamp"] = int(time.time() * 1000)
            query["recvWindow"] = 10000
            # The signature must use the exact same parameter order that requests sends.
            encoded = urlencode(query)
            query["signature"] = hmac.new(
                self.secret_key.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            headers["X-BX-APIKEY"] = self.api_key
        response = self.session.get(
            self.BASE_URL + path, params=query, headers=headers, timeout=self.timeout
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code", 0) != 0:
            raise RuntimeError(payload.get("msg") or "BingX API 回傳錯誤")
        return payload.get("data")

    def get_positions(self, symbol: str = "") -> List[Dict[str, Any]]:
        params = {"symbol": symbol} if symbol else None
        data = self._request("/openApi/swap/v2/user/positions", params, signed=True)
        if isinstance(data, dict):
            return data.get("positions", data.get("list", []))
        return data or []

    def get_balance(self, asset: str = "USDT") -> Dict[str, Any]:
        data = self._request("/openApi/swap/v3/user/balance", signed=True) or {}
        # v3 回傳每個資產一筆的 list；舊版可能是 dict 或 {"balance": {...}}
        if isinstance(data, dict):
            data = data.get("balance", data)
        if isinstance(data, list):
            if not data:
                return {}
            return next(
                (row for row in data if str(row.get("asset", "")).upper() == asset.upper()),
                data[0],
            )
        return data or {}

    def get_income(self, symbol: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        params = {"limit": min(max(limit, 1), 1000)}
        if symbol:
            params["symbol"] = symbol
        data = self._request("/openApi/swap/v2/user/income", params, signed=True)
        if isinstance(data, dict):
            return data.get("income", data.get("list", []))
        return data or []

    def get_premium_index(self, symbol: str) -> Dict[str, Any]:
        data = self._request(
            "/openApi/swap/v2/quote/premiumIndex", {"symbol": symbol}
        )
        if isinstance(data, list):
            return data[0] if data else {}
        return data or {}

    def get_funding_history(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        data = self._request(
            "/openApi/swap/v2/quote/fundingRate",
            {"symbol": symbol, "limit": min(max(limit, 1), 1000)},
        )
        if isinstance(data, dict):
            return data.get("fundingRates", data.get("list", []))
        return data or []


class BinanceReadOnlyClient:
    """幣安永續唯讀 client：只讀部位／餘額／資金費，不下單。

    同時支援兩種帳戶：
    - 統一帳戶（Portfolio Margin）：走 papi.binance.com 的 /papi/*，只需「啟用讀取」權限。
    - 一般合約帳戶：走 fapi.binance.com 的 /fapi/*，需要金鑰有合約權限。
    第一次呼叫時自動偵測並記住，之後不再重複探測。
    """

    BASE_URL = "https://fapi.binance.com"
    PAPI_URL = "https://papi.binance.com"

    def __init__(self, api_key: str = "", secret_key: str = "", timeout: int = 10):
        self.api_key = api_key or ""
        self.secret_key = secret_key or ""
        self.timeout = timeout
        self.session = requests.Session()
        self.logger = logging.getLogger("binance_read_only")
        self._mode = None  # 'papi'（統一帳戶）或 'fapi'（一般合約）

    @property
    def authenticated(self) -> bool:
        return bool(self.api_key and self.secret_key)

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None, signed=False,
                 base: Optional[str] = None):
        query = dict(params or {})
        headers = {}
        if signed:
            if not self.authenticated:
                raise RuntimeError("尚未設定幣安唯讀 API Key")
            query["timestamp"] = int(time.time() * 1000)
            query["recvWindow"] = 10000
            # 簽名必須與實際送出的參數順序完全一致
            encoded = urlencode(query)
            query["signature"] = hmac.new(
                self.secret_key.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256
            ).hexdigest()
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key
        response = self.session.get(
            (base or self.BASE_URL) + path, params=query, headers=headers, timeout=self.timeout
        )
        try:
            payload = response.json()
        except ValueError:
            response.raise_for_status()
            raise
        # 幣安錯誤格式：{"code": -2015, "msg": "Invalid API-key..."}
        if isinstance(payload, dict) and payload.get("msg") is not None:
            try:
                code = int(payload.get("code", 0))
            except (TypeError, ValueError):
                code = 0
            if code < 0:
                raise RuntimeError("幣安 API 錯誤 {}：{}".format(code, payload["msg"]))
        response.raise_for_status()
        return payload

    @property
    def mode(self) -> str:
        """偵測帳戶型態：統一帳戶回 'papi'，一般合約帳戶回 'fapi'（結果會快取）。"""
        if self._mode is None:
            try:
                self._request("/papi/v1/account", signed=True, base=self.PAPI_URL)
                self._mode = "papi"
                self.logger.info("幣安帳戶偵測為統一帳戶（Portfolio Margin）")
            except Exception:
                self._mode = "fapi"
                self.logger.info("幣安帳戶偵測為一般合約帳戶")
        return self._mode

    def get_positions(self, symbol: str = "") -> List[Dict[str, Any]]:
        """回傳未平倉部位。symbol 由呼叫端過濾，確保 UM／CM 都能涵蓋。"""
        rows: List[Dict[str, Any]] = []
        if self.mode == "papi":
            # UM = USDⓈ-M，CM = 幣本位；任一段失敗不影響另一段
            for path in ("/papi/v1/um/positionRisk", "/papi/v1/cm/positionRisk"):
                try:
                    rows.extend(self._request(path, signed=True, base=self.PAPI_URL) or [])
                except Exception as error:
                    self.logger.warning("讀取幣安 %s 失敗：%s", path, error)
        else:
            try:
                rows = self._request("/fapi/v2/positionRisk", signed=True) or []
            except Exception:
                # v2 若被下架則改用 v3（v3 無 leverage 欄位，前端會顯示 —）
                rows = self._request("/fapi/v3/positionRisk", signed=True) or []
        if symbol:
            rows = [r for r in rows if str(r.get("symbol")) == str(symbol)]
        return rows

    def get_balance(self, asset: str = "USDT") -> Dict[str, Any]:
        if self.mode == "papi":
            rows = self._request("/papi/v1/balance", signed=True, base=self.PAPI_URL) or []
            row = next(
                (r for r in rows if str(r.get("asset", "")).upper() == asset.upper()),
                rows[0] if rows else {},
            )
            result = {
                "asset": row.get("asset"),
                "balance": row.get("totalWalletBalance"),
                "availableBalance": row.get("crossMarginFree"),
            }
            try:
                account = self._request("/papi/v1/account", signed=True, base=self.PAPI_URL) or {}
                result["equity"] = account.get("accountEquity")
                result["uniMMR"] = account.get("uniMMR")
            except Exception as error:
                self.logger.warning("讀取幣安統一帳戶總覽失敗：%s", error)
            return result
        try:
            data = self._request("/fapi/v3/balance", signed=True)
        except Exception:
            data = self._request("/fapi/v2/balance", signed=True)
        if isinstance(data, list):
            if not data:
                return {}
            return next(
                (row for row in data if str(row.get("asset", "")).upper() == asset.upper()),
                data[0],
            )
        return data or {}

    def get_income(self, symbol: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        params = {"limit": min(max(limit, 1), 1000), "incomeType": "FUNDING_FEE"}
        if symbol:
            params["symbol"] = symbol
        if self.mode == "papi":
            return self._request(
                "/papi/v1/um/income", params, signed=True, base=self.PAPI_URL
            ) or []
        return self._request("/fapi/v1/income", params, signed=True) or []

    def get_premium_index(self, symbol: str) -> Dict[str, Any]:
        data = self._request("/fapi/v1/premiumIndex", {"symbol": symbol})
        if isinstance(data, list):
            return data[0] if data else {}
        return data or {}


class PionexReadOnlyClient:
    """派網（Pionex）唯讀 client：讀合約部位／餘額／資金費，不下單。

    合約 API 走 /uapi/v1/*（官方文件標示 Invite only，需先開通合約 API 權限）；
    現貨餘額走 /api/v1/*，且官方註明「不含機器人與理財帳戶」。
    兩者同一個 host、同一套簽名與回應格式。

    簽名（依官方文件）：
      1. timestamp（毫秒）放進 query
      2. 參數依 key 的 ASCII 升冪排序、以 & 串接，且不做 URL encode
      3. PATH_URL = path + "?" + 排序後參數
      4. signature = HMAC_SHA256(secret, METHOD + PATH_URL) 的 hex
      5. 帶入 PIONEX-KEY / PIONEX-SIGNATURE 標頭
    """

    BASE_URL = "https://api.pionex.com"

    def __init__(self, api_key: str = "", secret_key: str = "", timeout: int = 10):
        self.api_key = api_key or ""
        self.secret_key = secret_key or ""
        self.timeout = timeout
        self.session = requests.Session()
        self.logger = logging.getLogger("pionex_read_only")

    @property
    def authenticated(self) -> bool:
        return bool(self.api_key and self.secret_key)

    def _signed_get(self, path: str, params: Optional[Dict[str, Any]] = None):
        if not self.authenticated:
            raise RuntimeError("尚未設定派網唯讀 API Key")
        query = dict(params or {})
        query["timestamp"] = int(time.time() * 1000)
        # 簽名用的字串不可 URL encode，且需與實際送出的 query 完全一致
        sorted_query = "&".join("{}={}".format(k, query[k]) for k in sorted(query))
        path_url = "{}?{}".format(path, sorted_query)
        signature = hmac.new(
            self.secret_key.encode("utf-8"),
            ("GET" + path_url).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers = {"PIONEX-KEY": self.api_key, "PIONEX-SIGNATURE": signature}
        response = self.session.get(
            self.BASE_URL + path_url, headers=headers, timeout=self.timeout
        )
        try:
            payload = response.json()
        except ValueError:
            response.raise_for_status()
            raise
        if not payload.get("result", False):
            raise RuntimeError(
                "派網 API 錯誤 {}：{}".format(
                    payload.get("code", ""), payload.get("message") or payload
                )
            )
        response.raise_for_status()
        return payload.get("data") or {}

    def get_positions(self, symbol: str = "") -> List[Dict[str, Any]]:
        """合約未平倉部位（/uapi/v1/account/positions）。"""
        params = {"symbol": symbol} if symbol else None
        data = self._signed_get("/uapi/v1/account/positions", params)
        rows = data.get("positions", data) if isinstance(data, dict) else (data or [])
        return rows or []

    def get_futures_balance(self, coin: str = "USDT") -> Dict[str, Any]:
        """合約帳戶餘額（/uapi/v1/account/balances）。"""
        data = self._signed_get("/uapi/v1/account/balances")
        rows = data.get("balances", []) if isinstance(data, dict) else (data or [])
        return next(
            (r for r in rows if str(r.get("coin", "")).upper() == coin.upper()),
            rows[0] if rows else {},
        )

    def get_funding_fee(self, symbol: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        """資金費收付紀錄（/uapi/v1/trade/fundingFee，時間新到舊）。"""
        params = {"limit": min(max(limit, 1), 100)}
        if symbol:
            params["symbol"] = symbol
        data = self._signed_get("/uapi/v1/trade/fundingFee", params)
        rows = data.get("fundingFees", data) if isinstance(data, dict) else (data or [])
        return rows or []

    def get_balances(self, hide_zero: bool = True) -> List[Dict[str, Any]]:
        """現貨交易帳戶餘額（不含機器人／理財）。"""
        data = self._signed_get("/api/v1/account/balances")
        rows = data.get("balances", []) if isinstance(data, dict) else (data or [])
        result = []
        for row in rows:
            free = float(row.get("free") or 0)
            frozen = float(row.get("frozen") or 0)
            if hide_zero and free + frozen == 0:
                continue
            result.append({
                "coin": row.get("coin"),
                "free": free,
                "frozen": frozen,
                "total": free + frozen,
            })
        return sorted(result, key=lambda r: -r["total"])


class SinopacReadOnlyClient:
    """Lazy Shioaji wrapper. Importing the web app does not require Shioaji."""

    def __init__(self, api_key: str = "", secret_key: str = ""):
        self.api_key = api_key or ""
        self.secret_key = secret_key or ""
        self._api = None
        self.logger = logging.getLogger("sinopac_read_only")

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.secret_key)

    def _connect(self):
        if self._api is not None:
            return self._api
        if not self.configured:
            raise RuntimeError("尚未設定永豐 Shioaji API Key")
        try:
            import shioaji as sj
        except ImportError as error:
            raise RuntimeError("尚未安裝 shioaji 套件") from error
        api = sj.Shioaji(simulation=False)
        api.login(
            api_key=self.api_key,
            secret_key=self.secret_key,
            subscribe_trade=False,
        )
        self._api = api
        return api

    def get_stock_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        api = self._connect()
        import shioaji as sj

        positions = api.list_positions(account=api.stock_account, unit=sj.Unit.Share)
        for position in positions:
            if str(position.code) == str(symbol):
                return {
                    "symbol": str(position.code),
                    "quantity": float(position.quantity),
                    "entry_price": float(position.price),
                    "current_price": float(position.last_price),
                    "pnl": float(position.pnl),
                }
        return None

    def close(self):
        if self._api is not None:
            try:
                self._api.logout()
            finally:
                self._api = None
