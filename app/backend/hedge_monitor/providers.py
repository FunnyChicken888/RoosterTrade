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

    def get_balance(self) -> Dict[str, Any]:
        data = self._request("/openApi/swap/v3/user/balance", signed=True) or {}
        return data.get("balance", data)

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
