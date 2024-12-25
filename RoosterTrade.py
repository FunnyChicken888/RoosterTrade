import logging
import datetime
import time
import atexit
import requests
from config_utils import load_config, update_config_value
from max_trading_utils import get_price, get_account_balance, send_market_order, get_wallet_market_value
from max.client import Client

# Initialize logging
LOG_PATH = f"log/{datetime.date.today()}.log"
logging.basicConfig(
    format='%(asctime)s %(message)s',
    datefmt='%m/%d/%Y %I:%M:%S %p',
    filename=LOG_PATH,
    level=logging.INFO
)

# Load sensitive data from config.json
config = load_config()
TELEGRAM_BOT_TOKEN = config['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = config['TELEGRAM_CHAT_ID']
CLIENT_API_KEY = config['CLIENT_API_KEY']
CLIENT_SECRET_KEY = config['CLIENT_SECRET_KEY']

# Global constants
PROGRAM_VERSION = '20210705'

# Global state
buyFlagCount, sellFlagCount, balance, oldHour, oldWallet = 0, 0, 0, 0, 0

# Utility: Telegram notification
def telegram_notify_message(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        response = requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': msg})
        response.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Telegram Notify Error: {e}")

# Trade flag management
def read_trade_flag():
    global buyFlagCount, sellFlagCount
    try:
        with open(LOG_PATH, 'r') as f:
            data = f.read()
        buyFlagCount = data.count(f"{datetime.date.today()}_Buy_flag")
        sellFlagCount = data.count(f"{datetime.date.today()}_Sell_flag")
    except FileNotFoundError:
        logging.warning("Log file not found. No trades recorded yet.")

# Balance tracking
def track_balance(client, coin):
    global balance, oldHour, oldWallet
    wallet_value = get_wallet_market_value(client, coin)
    current_wallet = float(get_account_balance(client, coin)['balance'])

    if current_wallet != oldWallet:
        diff = current_wallet - oldWallet
        new_balance = balance + diff * get_price(client, coin)
        telegram_notify_message(
            f"{coin.upper()} wallet discrepancy detected.\nRecord: {oldWallet}, Wallet: {current_wallet}\n"
            f"Add to balance? Current Balance: {balance}, Add: {diff * get_price(client, coin)}\n"
            f"New balance percent: {wallet_value / new_balance}")
        if input(f"Update {coin.upper()} balance (Y/N):").lower() == 'y':
            balance = new_balance
            update_config_value('BalanceValue', balance)
        update_config_value(f'old{coin.capitalize()}Wallet', current_wallet)
        oldWallet = current_wallet

    money_percent = wallet_value / balance

    if datetime.datetime.now().hour != oldHour:
        telegram_notify_message(f"{coin.upper()} profit percentage: {money_percent}")
        oldHour = datetime.datetime.now().hour

    if money_percent < 0.95 and buyFlagCount < 3:
        diff = balance - wallet_value
        volume = round(diff / get_price(client, coin), 7)
        send_market_order(client, coin, volume, 'buy')
    elif money_percent > 1.05 and sellFlagCount < 3:
        diff = wallet_value - balance
        volume = round(diff / get_price(client, coin), 7)
        send_market_order(client, coin, volume, 'sell')

# Main execution
if __name__ == '__main__':
    client = Client(CLIENT_API_KEY, CLIENT_SECRET_KEY)
    balance = float(config.get('BalanceValue', 25000))
    oldWallet = float(config.get('oldWallet', 0))

    read_trade_flag()
    telegram_notify_message(f"Track balance started.\nProgram Version: {PROGRAM_VERSION}")
    atexit.register(lambda: telegram_notify_message("Tracking stopped."))

    while True:
        try:
            coin = input("Enter the coin you want to track (e.g., 'eth', 'btc'): ").strip().lower()
            track_balance(client, coin)
            time.sleep(10)
        except Exception as e:
            error_message = f"Exception: {e}"
            telegram_notify_message(error_message)
            logging.exception(error_message)
