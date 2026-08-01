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
