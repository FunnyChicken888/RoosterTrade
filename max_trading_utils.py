import logging
import datetime
from max.client import Client

def get_price(client, coin):
    """Get the current price of a coin in TWD."""
    result = client.get_public_markets_summary()
    return float(result['tickers'][f'{coin}twd']['last'])

def get_account_balance(client, coin):
    """Get the account balance for a specific coin."""
    result = client.get_private_account_balances()
    for data in result:
        if data['currency'] == coin:
            return data
    return None

def send_market_order(client, coin, volume, action):
    """Send a market order to buy or sell a coin."""
    order_type = 'buy' if action == 'buy' else 'sell'
    try:
        result = client.set_private_create_order(
            f"{coin}twd", order_type, volume, 'NONE', '', 'market')
        logging.info(f"{datetime.date.today()}_{action.capitalize()}_flag")
        return result
    except Exception as e:
        logging.error(f"Order Error: {e}")
        return None

def get_wallet_market_value(client, coin):
    """Calculate the market value of a coin wallet."""
    price = get_price(client, coin)
    balance = get_account_balance(client, coin)['balance']
    return float(price) * float(balance)
