from typing import Any, Dict


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate_hedge_metrics(portfolio: Dict[str, Any]) -> Dict[str, float]:
    """Calculate all values in TWD without making assumptions about contract size.

    ``perp_quantity`` is the number of contracts/units and ``contract_multiplier``
    is the amount of the quoted underlying represented by one unit.
    """
    spot_quantity = _number(portfolio.get("spot_quantity"))
    spot_entry = _number(portfolio.get("spot_entry_price"))
    spot_price = _number(portfolio.get("spot_current_price"), spot_entry)
    perp_quantity = abs(_number(portfolio.get("perp_quantity")))
    perp_entry = _number(portfolio.get("perp_entry_price"))
    perp_mark = _number(portfolio.get("perp_mark_price"), perp_entry)
    contract_multiplier = _number(portfolio.get("contract_multiplier"), 1.0)
    shares_per_underlying = _number(portfolio.get("shares_per_underlying"), 1.0)
    usdt_twd = _number(portfolio.get("usdt_twd"))
    funding_usdt = _number(portfolio.get("funding_received_usdt"))
    fees_twd = _number(portfolio.get("fees_twd"))

    spot_market_value = spot_quantity * spot_price
    spot_cost = spot_quantity * spot_entry
    spot_pnl = spot_market_value - spot_cost

    perp_underlying_quantity = perp_quantity * contract_multiplier
    perp_notional_usdt = perp_underlying_quantity * perp_mark
    perp_pnl_usdt = (perp_entry - perp_mark) * perp_underlying_quantity
    perp_pnl_twd = perp_pnl_usdt * usdt_twd
    funding_twd = funding_usdt * usdt_twd

    short_equivalent_shares = perp_underlying_quantity * shares_per_underlying
    net_exposure_shares = spot_quantity - short_equivalent_shares
    hedge_ratio = (
        short_equivalent_shares / spot_quantity if spot_quantity else 0.0
    )

    theoretical_underlying_usdt = 0.0
    premium_rate = 0.0
    if shares_per_underlying > 0 and usdt_twd > 0:
        theoretical_underlying_usdt = spot_price * shares_per_underlying / usdt_twd
        if theoretical_underlying_usdt:
            premium_rate = perp_mark / theoretical_underlying_usdt - 1.0

    total_pnl_twd = spot_pnl + perp_pnl_twd + funding_twd - fees_twd

    return {
        "spot_market_value_twd": spot_market_value,
        "spot_pnl_twd": spot_pnl,
        "perp_notional_usdt": perp_notional_usdt,
        "perp_notional_twd": perp_notional_usdt * usdt_twd,
        "perp_pnl_usdt": perp_pnl_usdt,
        "perp_pnl_twd": perp_pnl_twd,
        "funding_twd": funding_twd,
        "total_pnl_twd": total_pnl_twd,
        "short_equivalent_shares": short_equivalent_shares,
        "net_exposure_shares": net_exposure_shares,
        "hedge_ratio": hedge_ratio,
        "theoretical_underlying_usdt": theoretical_underlying_usdt,
        "premium_rate": premium_rate,
    }
