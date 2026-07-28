from flask import Flask, render_template, request, jsonify, redirect, url_for
import os
import sys
import json
import logging
from datetime import datetime

# 添加專案根目錄到 Python 路徑
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from max.client_v3 import ClientV3
from max.mock_client import MockClientV3
from backend.models.strategy_config import TradingStrategyConfig
from backend.strategies.strategy_manager import StrategyManager
from backend.utils.trading_record import TradingRecord
from backend.utils.config_loader import load_config
from backend.utils.paths import APP_DIR
from backend.services import twse_data, tw_backtest, twse_stocks, arb_status, tw_backtest_db

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


@app.route('/arb')
def arb_page():
    """套利風控監控儀表板（只示警、絕不下單）。"""
    return render_template('arb.html')


@app.route('/api/arb_status')
def api_arb_status():
    """回傳各空腿的距離強平／資金費率／急拉指標與示警等級，供前端輪詢。"""
    try:
        snap = arb_status.get_snapshot()
        return jsonify({"success": True, **snap})
    except FileNotFoundError:
        return jsonify({"success": False,
                        "error": "找不到 config/arb_monitor.json，請先依範本建立設定檔"})
    except json.JSONDecodeError as e:
        return jsonify({"success": False, "error": f"設定檔格式錯誤：{e}"})
    except Exception as e:
        app.logger.error(f"取得套利風控狀態失敗: {e}")
        return jsonify({"success": False, "error": str(e)})


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
