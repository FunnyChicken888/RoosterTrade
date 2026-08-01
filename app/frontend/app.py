from flask import Flask, render_template, request, jsonify, redirect, url_for
import os
import sys
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 添加專案根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from max.client_v3 import ClientV3
from max.mock_client import MockClientV3
from backend.models.strategy_config import TradingStrategyConfig
from backend.strategies.strategy_manager import StrategyManager
from backend.utils.trading_record import TradingRecord
from backend.utils.config_loader import load_config
from backend.utils.paths import APP_DIR
from backend.services import twse_data, tw_backtest, twse_stocks, tw_backtest_db
from backend.arb_monitor import risk_engine
from backend.hedge_monitor.providers import (
    BinanceReadOnlyClient, BingXReadOnlyClient, MaxPublicClient, SinopacReadOnlyClient
)
from backend.hedge_monitor.repository import HedgeRepository
from backend.hedge_monitor.service import HedgeMonitorService

app = Flask(__name__)
log_dir = os.path.join(APP_DIR, 'log')

# 確保日誌目錄存在
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, f'{datetime.now().strftime("%Y%m%d")}.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 載入設定（金鑰命名已正規化，並判斷是否進入 demo 模式）
config = load_config()
DEMO_MODE = config.get('demo_mode', False)

hedge_repository = HedgeRepository(
    os.getenv('HEDGE_DATABASE_PATH', os.path.join(APP_DIR, 'data', 'hedge_monitor.db'))
)
bingx_client = BingXReadOnlyClient(
    os.getenv('BINGX_API_KEY', config.get('bingx_api_key', '')),
    os.getenv('BINGX_SECRET_KEY', config.get('bingx_secret_key', '')),
)
binance_client = BinanceReadOnlyClient(
    os.getenv('BINANCE_API_KEY', config.get('binance_api_key', '')),
    os.getenv('BINANCE_SECRET_KEY', config.get('binance_secret_key', '')),
)
sinopac_client = SinopacReadOnlyClient(
    os.getenv('SHIOAJI_API_KEY', config.get('shioaji_api_key', '')),
    os.getenv('SHIOAJI_SECRET_KEY', config.get('shioaji_secret_key', '')),
)
hedge_monitor = HedgeMonitorService(
    hedge_repository, bingx_client, sinopac_client, MaxPublicClient()
)

# 支援的永續合約交易所（皆為唯讀，只讀部位不下單）
PERP_CLIENTS = {'bingx': bingx_client, 'binance': binance_client}
PERP_LABELS = {'bingx': 'BingX', 'binance': '幣安'}

# 初始化 MAX client：demo 模式用模擬資料，否則連真實交易所
if DEMO_MODE:
    app.logger.warning("以 DEMO 模式啟動：使用模擬行情與帳戶資料，不會送出真實交易")
    client = MockClientV3()
else:
    client = ClientV3(config['max_api_key'], config['max_secret_key'])

# 初始化 Telegram Bot 服務
from backend.services.telegram_bot import bot_service

# # 在應用關閉時停止bot服務
# @app.teardown_appcontext
# def shutdown_bot(error):
#     bot_service.stop()

# 檢查 MAX API 連線狀態
def check_max_api():
    try:
        # 嘗試獲取市場概況
        markets = client.get_market_summary()
        app.logger.debug(f"Markets response: {markets}")
        
        # 在市場列表中尋找BTC市場
        btc_market = next((market for market in markets if market['id'] == 'btctwd'), None)
        
        if btc_market:
            app.logger.info("MAX API連線成功")
            return True
        else:
            app.logger.error("無法獲取BTC市場數據")
            return False
    except Exception as e:
        app.logger.error(f"MAX API連線失敗: {str(e)}")
        return False

# 在應用啟動時檢查API連線並啟動服務
if not check_max_api():
    app.logger.error("無法連接到MAX API，請檢查API金鑰和網絡連接")
# else:
#     try:
#         bot_service.start()
#         app.logger.info("Telegram Bot服務已啟動")
#     except Exception as e:
#         app.logger.error(f"啟動Telegram Bot服務失敗: {e}")

strategy_manager = StrategyManager(client)


@app.context_processor
def inject_globals():
    """讓所有模板都能拿到 demo 旗標。"""
    return {"demo_mode": DEMO_MODE}


@app.route('/')
def index():
    """首頁 - 顯示所有策略概覽"""
    strategies = strategy_manager.get_all_strategies()
    return render_template('index.html', strategies=strategies)

@app.route('/strategy/new', methods=['GET', 'POST'])
def new_strategy():
    """新增策略頁面"""
    if request.method == 'POST':
        try:
            config = TradingStrategyConfig(
                strategy_name=request.form['strategy_name'],
                investment_amount=float(request.form['investment_amount']),
                max_position=float(request.form['max_position']),
                take_profit=float(request.form['take_profit']),
                auto_trade_percent=float(request.form['auto_trade_percent']),
                coin_type=request.form['coin_type'],
                # 這兩個欄位之前漏傳，導致表單填了也不會生效
                daily_trade_limit=int(request.form.get('daily_trade_limit', 5)),
                confirm_amount_threshold=float(request.form.get('confirm_amount_threshold', 0)),
                build_mode=request.form.get('build_mode', 'target'),
                target_open_price=float(request.form.get('target_open_price') or 0),
                is_active=bool(request.form.get('is_active', False))
            )
            if strategy_manager.create_strategy(config):
                return redirect(url_for('index'))
            return render_template('strategy.html', error="策略創建失敗")
        except Exception as e:
            return render_template('strategy.html', error=str(e))
    return render_template('strategy.html')

@app.route('/strategy/edit/<strategy_name>', methods=['GET', 'POST'])
def edit_strategy(strategy_name):
    """編輯策略頁面"""
    strategy = strategy_manager.get_strategy(strategy_name)
    if not strategy:
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            config = TradingStrategyConfig(
                strategy_name=strategy_name,
                investment_amount=float(request.form['investment_amount']),
                max_position=float(request.form['max_position']),
                take_profit=float(request.form['take_profit']),
                auto_trade_percent=float(request.form['auto_trade_percent']),
                coin_type=request.form['coin_type'],
                daily_trade_limit=int(request.form.get('daily_trade_limit', 5)),
                confirm_amount_threshold=float(request.form.get('confirm_amount_threshold', 0)),
                build_mode=request.form.get('build_mode', 'target'),
                target_open_price=float(request.form.get('target_open_price') or 0),
                is_active=bool(request.form.get('is_active', False))
            )
            if strategy_manager.update_strategy(config):
                return redirect(url_for('index'))
            return render_template('strategy.html', strategy=strategy.config, error="策略更新失敗")
        except Exception as e:
            return render_template('strategy.html', strategy=strategy.config, error=str(e))
    return render_template('strategy.html', strategy=strategy.config)

@app.route('/strategy/delete/<strategy_name>', methods=['POST'])
def delete_strategy(strategy_name):
    """刪除策略"""
    if strategy_manager.delete_strategy(strategy_name):
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "刪除策略失敗"})

@app.route('/history')
def trading_history():
    """交易歷史紀錄頁面"""
    strategies = strategy_manager.get_all_strategies()
    records = strategy_manager.get_trading_history()
    stats = strategy_manager.get_trading_stats()
    return render_template('history.html', 
                         strategies=strategies,
                         records=records,
                         stats=stats)


@app.route('/hedge-monitor')
def hedge_monitor_page():
    return render_template('hedge_monitor.html')


def _portfolio_payload(payload):
    numeric_fields = (
        'spot_quantity', 'spot_entry_price', 'spot_current_price',
        'perp_quantity', 'perp_entry_price', 'perp_mark_price',
        'contract_multiplier', 'shares_per_underlying', 'usdt_twd',
        'funding_received_usdt', 'fees_twd',
    )
    result = dict(payload)
    for field in numeric_fields:
        try:
            result[field] = float(payload.get(field, 0) or 0)
        except (TypeError, ValueError):
            raise ValueError('{} 必須是數字'.format(field))
    result.setdefault('spot_broker', 'sinopac')
    result.setdefault('perp_exchange', 'bingx')
    result['enabled'] = str(payload.get('enabled', 'true')).lower() not in ('0', 'false', 'off')
    return result


@app.route('/api/hedge-portfolios', methods=['GET', 'POST'])
def hedge_portfolios_api():
    try:
        if request.method == 'POST':
            payload = request.get_json(silent=True) or request.form.to_dict()
            portfolio_id = hedge_repository.save_portfolio(_portfolio_payload(payload))
            return jsonify({'success': True, 'id': portfolio_id}), 201
        refresh = request.args.get('refresh', '0') == '1'
        portfolios = [
            hedge_monitor.evaluate(portfolio, refresh=refresh)
            for portfolio in hedge_repository.list_portfolios()
        ]
        return jsonify({
            'success': True,
            'portfolios': portfolios,
            'connections': {
                'sinopac_configured': sinopac_client.configured,
                'bingx_configured': bingx_client.authenticated,
            },
        })
    except Exception as e:
        app.logger.exception('避險組合 API 執行失敗')
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/hedge-portfolios/<int:portfolio_id>', methods=['GET', 'PUT'])
def hedge_portfolio_api(portfolio_id):
    try:
        current = hedge_repository.get_portfolio(portfolio_id)
        if not current:
            return jsonify({'success': False, 'error': '找不到避險組合'}), 404
        if request.method == 'PUT':
            payload = request.get_json(silent=True) or request.form.to_dict()
            merged = dict(current)
            merged.update(payload)
            hedge_repository.save_portfolio(_portfolio_payload(merged), portfolio_id)
            current = hedge_repository.get_portfolio(portfolio_id)
        refresh = request.args.get('refresh', '0') == '1'
        return jsonify({
            'success': True,
            'result': hedge_monitor.evaluate(current, refresh=refresh),
        })
    except Exception as e:
        app.logger.exception('避險組合更新失敗')
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/hedge-portfolios/<int:portfolio_id>/snapshots')
def hedge_portfolio_snapshots_api(portfolio_id):
    if not hedge_repository.get_portfolio(portfolio_id):
        return jsonify({'success': False, 'error': '找不到避險組合'}), 404
    return jsonify({
        'success': True,
        'snapshots': hedge_repository.list_snapshots(
            portfolio_id, request.args.get('limit', 100)
        ),
    })


@app.route('/api/hedge-connections/bingx')
def bingx_connection_api():
    if not bingx_client.authenticated:
        return jsonify({
            'success': False, 'configured': False,
            'error': '尚未設定 BINGX_API_KEY 與 BINGX_SECRET_KEY',
        }), 400
    try:
        balance = bingx_client.get_balance()
        positions = bingx_client.get_positions()
        safe_balance = {
            key: balance.get(key) for key in (
                'asset', 'balance', 'equity', 'availableMargin',
                'usedMargin', 'unrealizedProfit'
            ) if balance.get(key) is not None
        }
        return jsonify({
            'success': True, 'configured': True,
            'message': 'BingX API 連線正常',
            'balance': safe_balance,
            'open_position_count': len(positions),
        })
    except Exception as e:
        app.logger.exception('BingX API 連線測試失敗')
        return jsonify({
            'success': False, 'configured': True, 'error': str(e),
        }), 502


@app.route('/api/hedge-connections/binance')
def binance_connection_api():
    if not binance_client.authenticated:
        return jsonify({
            'success': False, 'configured': False,
            'error': '尚未設定 BINANCE_API_KEY 與 BINANCE_SECRET_KEY',
        }), 400
    try:
        balance = binance_client.get_balance()
        positions = [p for p in binance_client.get_positions()
                     if _to_float(p.get('positionAmt')) != 0]
        safe_balance = {
            key: balance.get(key) for key in (
                'asset', 'balance', 'equity', 'uniMMR', 'crossWalletBalance',
                'crossUnPnl', 'availableBalance', 'maxWithdrawAmount'
            ) if balance.get(key) is not None
        }
        return jsonify({
            'success': True, 'configured': True,
            'message': '幣安 API 連線正常（{}）'.format(
                '統一帳戶' if binance_client.mode == 'papi' else '一般合約帳戶'),
            'balance': safe_balance,
            'open_position_count': len(positions),
        })
    except Exception as e:
        app.logger.exception('幣安 API 連線測試失敗')
        return jsonify({
            'success': False, 'configured': True, 'error': str(e),
        }), 502


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_position(exchange, p):
    """把各交易所的部位欄位正規化成同一種格式（BingX / 幣安欄位名不同）。"""
    amt = _to_float(p.get('positionAmt'))
    if amt == 0:
        return None  # 已平倉的殘留部位略過
    side = str(p.get('positionSide', '')).lower()
    if side in ('', 'both'):
        # 幣安單向持倉模式回傳 BOTH，方向看數量正負
        side = 'short' if amt < 0 else 'long'
    if exchange == 'binance':
        entry = _to_float(p.get('entryPrice'))
        unrealized = _to_float(p.get('unRealizedProfit'))
        realised = None                       # 幣安 positionRisk 不提供已實現
        margin = _to_float(p.get('isolatedMargin') or p.get('initialMargin'))
        if not margin:
            # 統一帳戶的 positionRisk 沒有保證金欄位，用名目/槓桿估算
            leverage = _to_float(p.get('leverage'))
            notional = abs(_to_float(p.get('notional')))
            if leverage:
                margin = notional / leverage
    else:
        entry = _to_float(p.get('avgPrice'))
        unrealized = _to_float(p.get('unrealizedProfit'))
        realised = _to_float(p.get('realisedProfit'))
        margin = _to_float(p.get('margin'))
    return {
        'exchange': exchange,
        'exchange_label': PERP_LABELS.get(exchange, exchange),
        'symbol': p.get('symbol'),
        'side': side,
        'position_amt': abs(amt),
        'entry_price': entry,
        'mark_price': _to_float(p.get('markPrice')),
        'liquidation_price': _to_float(p.get('liquidationPrice')),
        'unrealized_profit': unrealized,
        'realised_profit': realised,
        'pnl_ratio': _to_float(p.get('pnlRatio')),
        'margin': margin,
        'leverage': p.get('leverage'),
    }


def _collect_positions(exchange, client):
    """讀取單一交易所的未平倉部位，補上資金費率與風控示警。"""
    results = []
    for raw in client.get_positions():
        item = _normalize_position(exchange, raw)
        if item is None:
            continue
        funding_rate = None
        try:
            premium = client.get_premium_index(item['symbol'])
            funding_rate = _to_float(
                premium.get('lastFundingRate') or premium.get('fundingRate'), None
            )
        except Exception:
            app.logger.warning('讀取 %s %s 資金費率失敗', exchange, item['symbol'])
        item['funding_rate'] = funding_rate
        item['alerts'] = risk_engine.evaluate(
            {
                'label': '{} {}'.format(PERP_LABELS.get(exchange, exchange), item['symbol']),
                'side': item['side'],
                'liq_price': item['liquidation_price'],
            },
            {
                'mark': item['mark_price'],
                'funding_rate': funding_rate,
                'funding_interval_hours': 8,
            },
        )
        results.append(item)
    return results


@app.route('/api/hedge-connections/positions')
def perp_positions_api():
    """自動抓取所有已設定交易所（BingX／幣安）的合約部位並套用風控示警。

    只讀不下單：距離強平緩衝、資金費率異常、（有近期高低時）急拉／尬空。
    """
    positions = []
    connections = {}
    errors = []
    for exchange, client in PERP_CLIENTS.items():
        label = PERP_LABELS.get(exchange, exchange)
        if not client.authenticated:
            connections[exchange] = 'unconfigured'
            continue
        try:
            positions.extend(_collect_positions(exchange, client))
            connections[exchange] = 'ok'
        except Exception as e:
            app.logger.exception('%s 部位讀取失敗', label)
            connections[exchange] = 'error'
            errors.append('{}：{}'.format(label, e))
    if not any(state == 'ok' for state in connections.values()) and errors:
        return jsonify({'success': False, 'error': '；'.join(errors),
                        'connections': connections}), 502
    return jsonify({
        'success': True, 'positions': positions,
        'connections': connections, 'errors': errors,
    })


# 舊路徑保留相容（只回 BingX）
@app.route('/api/hedge-connections/bingx/positions')
def bingx_positions_api():
    if not bingx_client.authenticated:
        return jsonify({
            'success': False, 'configured': False,
            'error': '尚未設定 BINGX_API_KEY 與 BINGX_SECRET_KEY',
        }), 400
    try:
        return jsonify({'success': True,
                        'positions': _collect_positions('bingx', bingx_client)})
    except Exception as e:
        app.logger.exception('BingX 部位讀取失敗')
        return jsonify({'success': False, 'error': str(e)}), 502


def _usd_leg_payload(payload):
    numeric = ('quantity', 'avg_price', 'current_price', 'delta_factor', 'baseline_realized_usd')
    result = dict(payload)
    for field in numeric:
        try:
            result[field] = float(payload.get(field, 0) or 0)
        except (TypeError, ValueError):
            raise ValueError('{} 必須是數字'.format(field))
    if not result.get('delta_factor'):
        result['delta_factor'] = 1
    exchange = str(result.get('pair_exchange') or 'bingx').lower()
    if exchange not in PERP_CLIENTS:
        raise ValueError('不支援的交易所：{}'.format(exchange))
    result['pair_exchange'] = exchange
    return result


def _find_live_position(symbol, exchange='bingx'):
    """抓取指定交易所該合約目前的未平倉部位（找不到回 None，只讀不下單）。"""
    client = PERP_CLIENTS.get(str(exchange or 'bingx').lower())
    if not symbol or client is None or not client.authenticated:
        return None
    try:
        for p in client.get_positions(symbol):
            if str(p.get('symbol')) == str(symbol) and _to_float(p.get('positionAmt')) != 0:
                return _normalize_position(str(exchange).lower(), p)
    except Exception:
        app.logger.warning('讀取 %s 部位 %s 失敗', exchange, symbol)
    return None


def _usd_leg_metrics(leg):
    """美元層面的多腿×空腿對比。空腿已實現用『手動基準』避免換單失真，
    再加上 BingX 即時未實現，得到真實累計損益。"""
    quantity = _to_float(leg.get('quantity'))
    avg = _to_float(leg.get('avg_price'))
    current = _to_float(leg.get('current_price'))
    factor = _to_float(leg.get('delta_factor'), 1.0) or 1.0
    baseline = _to_float(leg.get('baseline_realized_usd'))
    long_value = quantity * current
    long_pnl = quantity * (current - avg)
    cost_basis = quantity * avg

    exchange = str(leg.get('pair_exchange') or 'bingx').lower()
    pos = _find_live_position(leg.get('pair_symbol'), exchange)
    short = None
    net_exposure = None
    hedge_ratio = None
    short_unrealized = 0.0
    if pos:
        amt = pos['position_amt']
        mark = pos['mark_price']
        short_unrealized = pos['unrealized_profit']
        short_notional = amt * mark
        short_exposure = short_notional * factor
        net_exposure = long_value - short_exposure
        hedge_ratio = short_exposure / long_value if long_value else None
        short = {
            'exchange': pos['exchange'],
            'exchange_label': pos['exchange_label'],
            'position_amt': amt,
            'mark_price': mark,
            'unrealized_profit': short_unrealized,
            'realised_profit_auto': pos.get('realised_profit'),
            'short_notional': short_notional,
            'short_exposure': short_exposure,
        }
    short_true_total = baseline + short_unrealized
    combined_pnl = long_pnl + short_true_total

    # 持有期間與年化報酬（以多腿成本 = 數量×均價 為基準）
    period_return = combined_pnl / cost_basis if cost_basis else None
    days_held = None
    annualized_return = None
    entry_date = leg.get('entry_date')
    if entry_date:
        try:
            start = datetime.strptime(str(entry_date)[:10], '%Y-%m-%d')
            days_held = (datetime.now() - start).days
            if days_held and days_held >= 1 and period_return is not None:
                annualized_return = period_return * 365.0 / days_held
        except ValueError:
            app.logger.warning('無法解析購入時間：%s', entry_date)

    return {
        'long_value': long_value,
        'long_pnl': long_pnl,
        'cost_basis': cost_basis,
        'baseline_realized_usd': baseline,
        'short': short,
        'short_true_total': short_true_total,
        'combined_pnl': combined_pnl,
        'net_exposure': net_exposure,
        'hedge_ratio': hedge_ratio,
        'period_return': period_return,
        'days_held': days_held,
        'annualized_return': annualized_return,
    }


@app.route('/api/usd-hedge-legs', methods=['GET', 'POST'])
def usd_hedge_legs_api():
    try:
        if request.method == 'POST':
            payload = request.get_json(silent=True) or request.form.to_dict()
            leg_id = hedge_repository.save_usd_leg(_usd_leg_payload(payload))
            return jsonify({'success': True, 'id': leg_id}), 201
        legs = [
            {**leg, 'metrics': _usd_leg_metrics(leg)}
            for leg in hedge_repository.list_usd_legs()
        ]
        return jsonify({
            'success': True, 'legs': legs,
            'bingx_configured': bingx_client.authenticated,
            'binance_configured': binance_client.authenticated,
        })
    except Exception as e:
        app.logger.exception('USD 多腿對比 API 失敗')
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/usd-hedge-legs/<int:leg_id>', methods=['PUT', 'DELETE'])
def usd_hedge_leg_api(leg_id):
    try:
        current = hedge_repository.get_usd_leg(leg_id)
        if not current:
            return jsonify({'success': False, 'error': '找不到多腿對比'}), 404
        if request.method == 'DELETE':
            hedge_repository.delete_usd_leg(leg_id)
            return jsonify({'success': True})
        payload = request.get_json(silent=True) or request.form.to_dict()
        merged = dict(current)
        merged.update(payload)
        hedge_repository.save_usd_leg(_usd_leg_payload(merged), leg_id)
        return jsonify({'success': True})
    except Exception as e:
        app.logger.exception('USD 多腿對比更新失敗')
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/api/usd-hedge-legs/<int:leg_id>/snapshot', methods=['POST'])
def usd_hedge_leg_snapshot_api(leg_id):
    leg = hedge_repository.get_usd_leg(leg_id)
    if not leg:
        return jsonify({'success': False, 'error': '找不到多腿對比'}), 404
    metrics = _usd_leg_metrics(leg)
    hedge_repository.add_usd_snapshot(leg_id, {'leg': leg, 'metrics': metrics})
    return jsonify({'success': True, 'metrics': metrics})


@app.route('/api/usd-hedge-legs/<int:leg_id>/snapshots')
def usd_hedge_leg_snapshots_api(leg_id):
    if not hedge_repository.get_usd_leg(leg_id):
        return jsonify({'success': False, 'error': '找不到多腿對比'}), 404
    return jsonify({
        'success': True,
        'snapshots': hedge_repository.list_usd_snapshots(
            leg_id, request.args.get('limit', 100)
        ),
    })


@app.route('/api/trading_history')
def get_trading_history():
    """獲取交易歷史記錄的API"""
    strategy_name = request.args.get('strategy_name')
    try:
        records = strategy_manager.get_trading_history(strategy_name)
        stats = strategy_manager.get_trading_stats(strategy_name)
        return jsonify({
            "success": True,
            "records": records,
            "stats": stats
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

@app.route('/api/check_connection', methods=['GET'])
def check_connection():
    """檢查MAX API連線狀態"""
    try:
        if check_max_api():
            return jsonify({
                "success": True,
                "message": "MAX API連線正常"
            })
        return jsonify({
            "success": False,
            "message": "無法連接到MAX API"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"檢查連線時發生錯誤: {str(e)}"
        })

@app.route('/api/execute_strategies', methods=['POST'])
def execute_strategies():
    """執行所有活躍的策略"""
    try:
        results = strategy_manager.execute_all_strategies()
        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/strategies', methods=['GET'])
def get_strategies():
    """獲取所有策略的實時數據"""
    try:
        strategies = strategy_manager.get_all_strategies()
        return jsonify(strategies)
    except Exception as e:
        app.logger.error(f"獲取策略數據時發生錯誤: {e}")
        return jsonify([])

@app.route('/backtest')
def backtest_page():
    """台股回測頁面：用真實台股行情 + 台股費稅模擬定值再平衡策略。"""
    return render_template('backtest.html')


@app.route('/api/tw_stocks')
def api_tw_stocks():
    """上市公司清單（代號 + 簡稱），供回測頁自動完成與依公司名搜尋。"""
    try:
        return jsonify({"success": True, "stocks": twse_stocks.get_stock_list()})
    except Exception as e:
        app.logger.error(f"取得上市公司清單失敗: {e}")
        return jsonify({"success": False, "error": str(e), "stocks": []})

@app.route('/api/tw_price')
def api_tw_price():
    """回傳某股票最新收盤價與公司名，供回測頁的手續費門檻試算（依股價換算股數）。"""
    stock_no = str(request.args.get('stock_no', '')).strip()
    if not stock_no:
        return jsonify({"success": False, "error": "缺少股票代號"})
    try:
        prices = twse_data.fetch_daily_ohlc(stock_no, 1)
        return jsonify({"success": True, "stock_no": stock_no,
                        "name": twse_stocks.get_name(stock_no),
                        "price": prices[-1]["close"]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/backtest_tw', methods=['POST'])
def api_backtest_tw():
    """執行台股回測。參數見前端表單；band 可傳逗號分隔多值做掃描。"""
    try:
        body = request.get_json(force=True) or {}
        stock_no = str(body.get('stock_no', '')).strip()
        if not stock_no:
            return jsonify({"success": False, "error": "請輸入股票代號"})

        months = int(body.get('months', 12))
        investment_amount = float(body.get('investment_amount', 1000000))
        max_position = float(body.get('max_position', 0))
        fee_discount = float(body.get('fee_discount', 0.6))
        fee_min = float(body.get('fee_min', 20))
        security_type = str(body.get('security_type', 'common'))

        # band 支援單一數字或逗號分隔多值
        raw_bands = body.get('bands', body.get('auto_trade_percent', 3))
        if isinstance(raw_bands, str):
            bands = [float(b) for b in raw_bands.split(',') if b.strip()]
        elif isinstance(raw_bands, (list, tuple)):
            bands = [float(b) for b in raw_bands]
        else:
            bands = [float(raw_bands)]
        bands = sorted(set(bands)) or [3.0]

        prices = twse_data.fetch_daily_ohlc(stock_no, months)
        costs = tw_backtest.make_costs(fee_discount, fee_min, security_type)
        results = tw_backtest.run_sweep(prices, investment_amount, max_position, bands, costs)

        return jsonify({
            "success": True,
            "stock_no": stock_no,
            "stock_name": twse_stocks.get_name(stock_no),
            "start": prices[0]["date"],
            "end": prices[-1]["date"],
            "days": len(prices),
            "price_start": prices[0]["close"],
            "price_end": prices[-1]["close"],
            "costs": {"fee_rate": costs["fee_rate"], "fee_min": costs["fee_min"],
                      "tax_rate": costs["tax_rate"], "security_type": security_type},
            "results": results,
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)})
    except Exception as e:
        app.logger.error(f"台股回測發生錯誤: {e}")
        return jsonify({"success": False, "error": f"回測失敗: {e}"})


@app.route('/api/backtest_tw_db')
def api_backtest_tw_db():
    """查詢批次台股回測資料庫，供前端 ROI 排行與篩選。"""
    try:
        run_id = request.args.get('run_id') or None
        data = tw_backtest_db.query_results(
            run_id=int(run_id) if run_id else None,
            q=request.args.get('q', '').strip(),
            band=request.args.get('band'),
            min_roi=request.args.get('min_roi'),
            max_trades=request.args.get('max_trades'),
            status=request.args.get('status', 'ok'),
            sort_by=request.args.get('sort_by', 'roi'),
            order=request.args.get('order', 'desc'),
            limit=request.args.get('limit', 100),
            offset=request.args.get('offset', 0),
        )
        return jsonify({"success": True, **data})
    except Exception as e:
        app.logger.error(f"查詢台股回測資料庫失敗: {e}")
        return jsonify({"success": False, "error": str(e), "rows": [], "total": 0})


if __name__ == '__main__':
    # 直接執行此檔案時的開發入口（正式啟動請用 app/run.py 或 gunicorn）
    app.run(host='0.0.0.0', debug=False, port=5003, threaded=True)
