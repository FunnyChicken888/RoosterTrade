import logging
import threading
import time
from typing import Any, Dict

from .calculator import calculate_hedge_metrics


class HedgeMonitorService:
    def __init__(self, repository, bingx_client, sinopac_client, max_client=None):
        self.repository = repository
        self.bingx = bingx_client
        self.sinopac = sinopac_client
        self.max = max_client
        self.logger = logging.getLogger("hedge_monitor")
        self._refresh_lock = threading.Lock()
        self._collector_thread = None
        self._collector_stop = threading.Event()

    @staticmethod
    def _float(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def evaluate(self, portfolio: Dict[str, Any], refresh: bool = False) -> Dict[str, Any]:
        if refresh:
            with self._refresh_lock:
                return self._evaluate(portfolio, refresh=True)
        return self._evaluate(portfolio, refresh=False)

    def _evaluate(self, portfolio: Dict[str, Any], refresh: bool = False) -> Dict[str, Any]:
        data = dict(portfolio)
        warnings = []
        source_status = {"sinopac": "manual", "bingx": "manual", "fx": "manual"}

        if refresh and self.sinopac.configured:
            try:
                position = self.sinopac.get_stock_position(data["spot_symbol"])
                if position:
                    data["spot_quantity"] = position["quantity"]
                    data["spot_entry_price"] = position["entry_price"]
                    data["spot_current_price"] = position["current_price"]
                    source_status["sinopac"] = "live"
                else:
                    warnings.append("永豐帳戶中找不到指定的現貨部位")
            except Exception as error:
                warnings.append("永豐同步失敗：{}".format(error))

        if refresh:
            if self.max is not None:
                try:
                    fx_quote = self.max.get_usdt_twd()
                    data["usdt_twd"] = fx_quote["rate"]
                    data["fx_quote"] = fx_quote
                    source_status["fx"] = "MAX-live"
                except Exception as error:
                    warnings.append("MAX USDT/TWD 同步失敗，沿用手動匯率：{}".format(error))

            try:
                premium = self.bingx.get_premium_index(data["perp_symbol"])
                mark_price = premium.get("markPrice") or premium.get("price")
                if mark_price is not None:
                    data["perp_mark_price"] = self._float(mark_price)
                    source_status["bingx"] = "public-live"
                data["funding_rate"] = self._float(
                    premium.get("lastFundingRate") or premium.get("fundingRate")
                )
                data["next_funding_time"] = premium.get("nextFundingTime")
            except Exception as error:
                warnings.append("BingX 行情同步失敗：{}".format(error))

            if self.bingx.authenticated:
                try:
                    positions = self.bingx.get_positions(data["perp_symbol"])
                    short = next(
                        (p for p in positions if str(p.get("positionSide", "")).upper() == "SHORT"),
                        positions[0] if positions else None,
                    )
                    if short:
                        data["perp_quantity"] = abs(self._float(short.get("positionAmt")))
                        data["perp_entry_price"] = self._float(
                            short.get("avgPrice") or short.get("entryPrice")
                        )
                        data["liquidation_price"] = self._float(short.get("liquidationPrice"))
                        data["margin"] = self._float(short.get("initialMargin"))
                        source_status["bingx"] = "account-live"

                    income = self.bingx.get_income(data["perp_symbol"], limit=1000)
                    funding_rows = [
                        row for row in income
                        if "FUND" in str(row.get("incomeType", row.get("type", ""))).upper()
                    ]
                    data["funding_received_usdt"] = sum(
                        self._float(row.get("income")) for row in funding_rows
                    )
                except Exception as error:
                    warnings.append("BingX 帳戶同步失敗：{}".format(error))

        metrics = calculate_hedge_metrics(data)
        result = {
            "portfolio": data,
            "metrics": metrics,
            "source_status": source_status,
            "warnings": warnings,
        }
        if refresh and data.get("id"):
            self.repository.add_snapshot(int(data["id"]), result)
        return result

    def collect_once(self):
        results = []
        for portfolio in self.repository.list_portfolios():
            if portfolio.get("enabled"):
                try:
                    results.append(self.evaluate(portfolio, refresh=True))
                except Exception:
                    self.logger.exception("避險組合 %s 採集失敗", portfolio.get("id"))
        return results

    def start_collector(self, interval_seconds: int = 60):
        if self._collector_thread and self._collector_thread.is_alive():
            return
        interval_seconds = max(int(interval_seconds), 15)
        self._collector_stop.clear()

        def loop():
            while not self._collector_stop.is_set():
                started = time.time()
                self.collect_once()
                remaining = max(0, interval_seconds - (time.time() - started))
                self._collector_stop.wait(remaining)

        self._collector_thread = threading.Thread(
            target=loop, name="hedge-monitor-collector", daemon=True
        )
        self._collector_thread.start()
        self.logger.info("避險資料採集器已啟動，間隔 %s 秒", interval_seconds)

    def stop_collector(self):
        self._collector_stop.set()
        if self._collector_thread and self._collector_thread.is_alive():
            self._collector_thread.join(timeout=10)
        self._collector_thread = None
        self.sinopac.close()
