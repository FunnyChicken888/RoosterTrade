from flask import Flask, render_template, request, jsonify, redirect, url_for
import os
import sys
import json
import logging
from datetime import datetime

# 添加專案根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from max.client_v3 import ClientV3
from backend.models.strategy_config import TradingStrategyConfig
from backend.strategies.strategy_manager import StrategyManager
from backend.utils.trading_record import TradingRecord

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
    # 獲取當前文件的目錄路徑
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(current_dir, 'config','config.json')
    log_dir = os.path.abspath(log_dir)  # 取得絕對路徑，避免相對路徑問題
    with open(log_dir, 'r') as f:
        config = json.load(f)
        CLIENT_API_KEY = config.get('max_api_key', '')
        CLIENT_SECRET_KEY = config.get('max_secret_key', '')
except FileNotFoundError:
    app.logger.error("找不到config.json文件，請確保文件存在並包含正確的API金鑰")
    CLIENT_API_KEY = ''
    CLIENT_SECRET_KEY = ''
except json.JSONDecodeError:
    app.logger.error("config.json格式錯誤")
    CLIENT_API_KEY = ''
    CLIENT_SECRET_KEY = ''

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

if __name__ == '__main__':
    import os
    import sys
    # 確保可以從任何目錄運行
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # 設置環境變量
    os.environ['FLASK_APP'] = 'frontend.app'
    app.run(debug=True, port=5000)
