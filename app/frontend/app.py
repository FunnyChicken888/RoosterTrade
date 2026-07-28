from flask import Flask, render_template, request, jsonify, redirect, url_for
import os
import sys
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

# 本機執行時從專案根目錄 .env 載入憑證；既有系統環境變數優先。
load_dotenv()

# 添加專案根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from max.client_v3 import ClientV3
from backend.models.strategy_config import TradingStrategyConfig
from backend.strategies.strategy_manager import StrategyManager
from backend.utils.trading_record import TradingRecord
from backend.hedge_monitor.providers import (
    BingXReadOnlyClient, MaxPublicClient, SinopacReadOnlyClient
)
from backend.hedge_monitor.repository import HedgeRepository
from backend.hedge_monitor.service import HedgeMonitorService

app = Flask(__name__)
# 獲取當前文件的目錄路徑
current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log_dir = os.path.join(current_dir, 'log')

# 確保日誌目錄存在
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, f'{datetime.now().strftime("%Y%m%d")}.log')),
        logging.StreamHandler()
    ]
)

# 從配置檔案載入 API 金鑰
try:
    # 添加後端模組路徑
    sys.path.append(os.path.join(current_dir, '..'))
    from backend.utils.config_loader import ConfigLoader
    
    config, config_path = ConfigLoader.load_config()
    app.logger.info(f"成功載入配置文件: {config_path}")
    
    CLIENT_API_KEY = os.getenv('MAX_API_KEY', config.get('max_api_key', ''))
    CLIENT_SECRET_KEY = os.getenv('MAX_SECRET_KEY', config.get('max_secret_key', ''))
    
    if not CLIENT_API_KEY or not CLIENT_SECRET_KEY:
        app.logger.warning("API金鑰為空，將使用測試模式")
except Exception as e:
    app.logger.error(f"載入配置時發生錯誤: {e}")
    CLIENT_API_KEY = ''
    CLIENT_SECRET_KEY = ''

# 避險監控只使用唯讀憑證；環境變數優先，設定檔作為本機相容方式。
hedge_config = config if 'config' in globals() else {}
hedge_repository = HedgeRepository(
    os.getenv('HEDGE_DATABASE_PATH', os.path.join(current_dir, 'data', 'hedge_monitor.db'))
)
bingx_client = BingXReadOnlyClient(
    os.getenv('BINGX_API_KEY', hedge_config.get('bingx_api_key', '')),
    os.getenv('BINGX_SECRET_KEY', hedge_config.get('bingx_secret_key', '')),
)
sinopac_client = SinopacReadOnlyClient(
    os.getenv('SHIOAJI_API_KEY', hedge_config.get('shioaji_api_key', '')),
    os.getenv('SHIOAJI_SECRET_KEY', hedge_config.get('shioaji_secret_key', '')),
)
max_public_client = MaxPublicClient()
hedge_monitor = HedgeMonitorService(
    hedge_repository, bingx_client, sinopac_client, max_public_client
)

# 初始化 MAX client 和策略管理器
client = ClientV3(CLIENT_API_KEY, CLIENT_SECRET_KEY)

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
                coin_type=request.form['coin_type']
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
    """跨市場避險組合監控頁面。"""
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


@app.route('/api/hedge-connections/bingx', methods=['GET'])
def bingx_connection_api():
    """驗證 BingX 唯讀憑證，不回傳任何敏感欄位。"""
    if not bingx_client.authenticated:
        return jsonify({
            'success': False,
            'configured': False,
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
            'success': True,
            'configured': True,
            'message': 'BingX API 連線正常',
            'balance': safe_balance,
            'open_position_count': len(positions),
        })
    except Exception as e:
        app.logger.exception('BingX API 連線測試失敗')
        return jsonify({
            'success': False,
            'configured': True,
            'error': str(e),
        }), 502

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

@app.route('/api/markets', methods=['GET'])
def get_markets():
    """獲取可交易的幣種列表"""
    try:
        markets = client.get_market_summary()
        app.logger.debug(f"Markets response: {markets}")
        
        # 處理市場數據，提取幣種信息
        coin_options = []
        for market in markets:
            # MAX API返回的市場格式通常是 'btctwd', 'ethtwd' 等
            market_id = market.get('id', '').upper()
            if market_id.endswith('TWD'):
                # 提取幣種名稱（去掉TWD後綴）
                coin_symbol = market_id.replace('TWD', '')
                coin_name = market.get('name', coin_symbol)
                
                # 檢查市場是否活躍
                if market.get('state') == 'active':
                    coin_options.append({
                        'symbol': coin_symbol,
                        'name': coin_name,
                        'market_id': market_id.lower(),
                        'display_name': f"{coin_name} ({coin_symbol})"
                    })
        
        # 如果沒有獲取到市場數據，提供模擬數據用於測試
        if not coin_options:
            app.logger.warning("未獲取到真實市場數據，使用模擬數據")
            coin_options = [
                {
                    'symbol': 'BTC',
                    'name': 'Bitcoin',
                    'market_id': 'btctwd',
                    'display_name': 'Bitcoin (BTC)'
                },
                {
                    'symbol': 'ETH',
                    'name': 'Ethereum',
                    'market_id': 'ethtwd',
                    'display_name': 'Ethereum (ETH)'
                },
                {
                    'symbol': 'USDT',
                    'name': 'Tether',
                    'market_id': 'usdttwd',
                    'display_name': 'Tether (USDT)'
                },
                {
                    'symbol': 'ADA',
                    'name': 'Cardano',
                    'market_id': 'adatwd',
                    'display_name': 'Cardano (ADA)'
                },
                {
                    'symbol': 'DOT',
                    'name': 'Polkadot',
                    'market_id': 'dottwd',
                    'display_name': 'Polkadot (DOT)'
                }
            ]
        
        # 按幣種符號排序
        coin_options.sort(key=lambda x: x['symbol'])
        
        app.logger.info(f"成功獲取 {len(coin_options)} 個可交易幣種")
        return jsonify({
            "success": True,
            "markets": coin_options
        })
    except Exception as e:
        app.logger.error(f"獲取市場數據時發生錯誤: {e}")
        # 在發生錯誤時也提供備用數據
        backup_options = [
            {
                'symbol': 'BTC',
                'name': 'Bitcoin',
                'market_id': 'btctwd',
                'display_name': 'Bitcoin (BTC)'
            },
            {
                'symbol': 'ETH',
                'name': 'Ethereum',
                'market_id': 'ethtwd',
                'display_name': 'Ethereum (ETH)'
            },
            {
                'symbol': 'USDT',
                'name': 'Tether',
                'market_id': 'usdttwd',
                'display_name': 'Tether (USDT)'
            }
        ]
        return jsonify({
            "success": True,
            "markets": backup_options,
            "note": "使用備用幣種列表"
        })

if __name__ == '__main__':
    import os
    import sys
    # 確保可以從任何目錄運行
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # 設置環境變量
    os.environ['FLASK_APP'] = 'frontend.app'
    app.run(debug=True, port=5000)
