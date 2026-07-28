import os
import tempfile
import unittest
from unittest.mock import Mock

from ..hedge_monitor.calculator import calculate_hedge_metrics
from ..hedge_monitor.providers import MaxPublicClient
from ..hedge_monitor.repository import HedgeRepository


class TestHedgeCalculator(unittest.TestCase):
    def test_tsm_short_hedge_and_twd_pnl(self):
        result = calculate_hedge_metrics({
            "spot_quantity": 500,
            "spot_entry_price": 1000,
            "spot_current_price": 1100,
            "perp_quantity": 100,
            "perp_entry_price": 160,
            "perp_mark_price": 150,
            "contract_multiplier": 1,
            "shares_per_underlying": 5,
            "usdt_twd": 32,
            "funding_received_usdt": 25,
            "fees_twd": 200,
        })
        self.assertEqual(result["short_equivalent_shares"], 500)
        self.assertEqual(result["net_exposure_shares"], 0)
        self.assertEqual(result["hedge_ratio"], 1)
        self.assertEqual(result["spot_pnl_twd"], 50000)
        self.assertEqual(result["perp_pnl_twd"], 32000)
        self.assertEqual(result["funding_twd"], 800)
        self.assertEqual(result["total_pnl_twd"], 82600)

    def test_premium_uses_adr_share_ratio_and_fx(self):
        result = calculate_hedge_metrics({
            "spot_quantity": 5,
            "spot_current_price": 960,
            "perp_mark_price": 160,
            "shares_per_underlying": 5,
            "usdt_twd": 30,
        })
        self.assertEqual(result["theoretical_underlying_usdt"], 160)
        self.assertEqual(result["premium_rate"], 0)


class TestHedgeRepository(unittest.TestCase):
    def test_save_and_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = HedgeRepository(os.path.join(directory, "hedge.db"))
            portfolio_id = repository.save_portfolio({
                "name": "TSMC hedge", "spot_broker": "sinopac",
                "spot_symbol": "2330", "spot_quantity": 500,
                "spot_entry_price": 1000, "spot_current_price": 1010,
                "perp_exchange": "bingx", "perp_symbol": "TSMU-USDT",
                "perp_quantity": 100, "perp_entry_price": 160,
                "perp_mark_price": 159, "contract_multiplier": 1,
                "shares_per_underlying": 5, "usdt_twd": 32,
                "funding_received_usdt": 0, "fees_twd": 0, "enabled": True,
            })
            self.assertEqual(repository.get_portfolio(portfolio_id)["spot_symbol"], "2330")
            repository.add_snapshot(portfolio_id, {"metrics": {"total_pnl_twd": 1}})
            snapshots = repository.list_snapshots(portfolio_id)
            self.assertEqual(snapshots[0]["metrics"]["total_pnl_twd"], 1)


class TestMaxPublicClient(unittest.TestCase):
    def test_usdt_twd_uses_latest_trade_and_preserves_spread(self):
        response = Mock()
        response.json.return_value = {
            "at": 1234567890,
            "ticker": {"last": "32.45", "buy": "32.44", "sell": "32.46"},
        }
        response.raise_for_status.return_value = None
        client = MaxPublicClient()
        client.session.get = Mock(return_value=response)

        quote = client.get_usdt_twd()

        self.assertEqual(quote["rate"], 32.45)
        self.assertEqual(quote["bid"], 32.44)
        self.assertEqual(quote["ask"], 32.46)
        client.session.get.assert_called_once_with(
            "https://max-api.maicoin.com/api/v2/tickers/usdttwd", timeout=10
        )


if __name__ == "__main__":
    unittest.main()
