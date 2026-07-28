"""批次建立台股回測資料庫。

範例：
  PYTHONPATH=app .venv/bin/python scripts/build_tw_backtest_db.py
  PYTHONPATH=app .venv/bin/python scripts/build_tw_backtest_db.py --months 24 --bands 3,5,8 --limit 50

資料會寫入 app/records/tw_backtest.sqlite3。抓行情會打 TWSE 公開 API，首次跑全市場
需要較久；若中斷，可用 --resume RUN_ID 接續同一批。--max-position 0 代表不設加碼上限。
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))

from backend.services import tw_backtest, twse_data, twse_stocks, tw_backtest_db


def parse_bands(raw):
    bands = [float(x.strip()) for x in str(raw).split(",") if x.strip()]
    return sorted(set(bands)) or [3.0]


def build_params(args):
    return {
        "months": int(args.months),
        "investment_amount": float(args.investment_amount),
        "max_position": float(args.max_position),
        "bands": parse_bands(args.bands),
        "fee_discount": float(args.fee_discount),
        "fee_min": float(args.fee_min),
        "security_type": args.security_type,
    }


def main():
    p = argparse.ArgumentParser(description="建立台股批次回測 SQLite 資料庫")
    p.add_argument("--months", type=int, default=12)
    p.add_argument("--investment-amount", type=float, default=1000000)
    p.add_argument("--max-position", type=float, default=0, help="0 代表不設加碼上限")
    p.add_argument("--bands", default="3,5,8,10")
    p.add_argument("--fee-discount", type=float, default=0.6)
    p.add_argument("--fee-min", type=float, default=20)
    p.add_argument("--security-type", choices=["common", "etf", "daytrade"], default="common")
    p.add_argument("--stock", action="append", help="只跑指定代號，可重複傳入")
    p.add_argument("--limit", type=int, default=0, help="只跑前 N 檔，測試用")
    p.add_argument("--sleep", type=float, default=0.35, help="每檔股票間隔秒數，避免打太快")
    p.add_argument("--resume", type=int, default=0, help="接續既有 run_id，已存在的股票會跳過")
    args = p.parse_args()

    params = build_params(args)
    conn = tw_backtest_db.connect()
    tw_backtest_db.init_db(conn)

    all_stocks = twse_stocks.get_stock_list()
    if args.stock:
        wanted = {str(s).strip() for s in args.stock}
        stocks = [s for s in all_stocks if s["code"] in wanted]
        missing = sorted(wanted - {s["code"] for s in stocks})
        stocks.extend({"code": code, "name": twse_stocks.get_name(code)} for code in missing)
    else:
        stocks = all_stocks
    if args.limit:
        stocks = stocks[:args.limit]

    if not stocks:
        raise SystemExit("沒有股票清單可跑，請確認網路或 app/records/twse_stock_list.json 快取")

    run_id = args.resume or tw_backtest_db.create_run(params, len(stocks), conn)
    costs = tw_backtest.make_costs(params["fee_discount"], params["fee_min"], params["security_type"])
    print(f"run_id={run_id} stocks={len(stocks)} db={tw_backtest_db.db_path()}")

    ok = 0
    fail = 0
    skipped = 0
    for idx, stock in enumerate(stocks, 1):
        code = stock["code"]
        name = stock.get("name", "")
        if args.resume and tw_backtest_db.has_stock_result(run_id, code, conn):
            skipped += 1
            print(f"[{idx}/{len(stocks)}] skip {code} {name}")
            continue

        try:
            prices = twse_data.fetch_daily_ohlc(code, params["months"])
            results = tw_backtest.run_sweep(
                prices, params["investment_amount"], params["max_position"], params["bands"], costs
            )
            tw_backtest_db.save_stock_results(run_id, code, name, prices, params, results, conn)
            ok += 1
            best = max(results, key=lambda r: r["roi"])
            print(f"[{idx}/{len(stocks)}] ok {code} {name} best={best['band']}% roi={best['roi']}%")
        except Exception as e:
            fail += 1
            tw_backtest_db.save_stock_error(run_id, code, name, params, e, conn)
            print(f"[{idx}/{len(stocks)}] fail {code} {name}: {e}")

        if args.sleep > 0:
            time.sleep(args.sleep)

    tw_backtest_db.finish_run(run_id, conn)
    conn.close()
    print(f"done run_id={run_id} ok={ok} fail={fail} skipped={skipped}")


if __name__ == "__main__":
    main()
