"""台股批次回測結果資料庫。

使用 SQLite 存放「所有上市股票 × 多個 band」的回測摘要，讓前端可以快速排序、
篩選 ROI，而不用每次開頁面都重新抓證交所行情。
"""
import json
import os
import sqlite3
import time

from ..utils.paths import records_dir


SORT_COLUMNS = {
    "roi", "profit", "buy_hold_roi", "vs_buy_hold", "n_trades",
    "total_fee", "total_tax", "peak_invested", "price_change_pct",
    "stock_no", "stock_name", "band", "updated_at",
}


def db_path():
    return os.path.join(records_dir(), "tw_backtest.sqlite3")


def connect(path=None):
    conn = sqlite3.connect(path or db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn=None):
    own = conn is None
    conn = conn or connect()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS tw_backtest_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at REAL NOT NULL,
        params_json TEXT NOT NULL,
        stock_count INTEGER NOT NULL DEFAULT 0,
        finished_at REAL,
        ok_count INTEGER NOT NULL DEFAULT 0,
        fail_count INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS tw_backtest_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        stock_no TEXT NOT NULL,
        stock_name TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'ok',
        error TEXT NOT NULL DEFAULT '',
        band REAL,
        months INTEGER NOT NULL,
        start_date TEXT,
        end_date TEXT,
        days INTEGER NOT NULL DEFAULT 0,
        price_start REAL,
        price_end REAL,
        price_change_pct REAL,
        investment_amount REAL NOT NULL,
        max_position REAL NOT NULL,
        fee_discount REAL NOT NULL,
        fee_min REAL NOT NULL,
        security_type TEXT NOT NULL,
        n_trades INTEGER,
        total_fee REAL,
        total_tax REAL,
        net_invested REAL,
        peak_invested REAL,
        final_shares INTEGER,
        final_value REAL,
        profit REAL,
        roi REAL,
        buy_hold_profit REAL,
        buy_hold_roi REAL,
        vs_buy_hold REAL,
        updated_at REAL NOT NULL,
        FOREIGN KEY(run_id) REFERENCES tw_backtest_runs(id)
    );

    CREATE INDEX IF NOT EXISTS idx_tw_bt_results_run_roi
        ON tw_backtest_results(run_id, status, roi DESC);
    CREATE INDEX IF NOT EXISTS idx_tw_bt_results_stock
        ON tw_backtest_results(stock_no);
    CREATE INDEX IF NOT EXISTS idx_tw_bt_results_band
        ON tw_backtest_results(run_id, band);
    """)
    conn.commit()
    if own:
        conn.close()


def create_run(params, stock_count, conn=None):
    own = conn is None
    conn = conn or connect()
    init_db(conn)
    cur = conn.execute(
        "INSERT INTO tw_backtest_runs (created_at, params_json, stock_count) VALUES (?, ?, ?)",
        (time.time(), json.dumps(params, ensure_ascii=False, sort_keys=True), int(stock_count)),
    )
    conn.commit()
    run_id = cur.lastrowid
    if own:
        conn.close()
    return run_id


def finish_run(run_id, conn=None):
    own = conn is None
    conn = conn or connect()
    ok = conn.execute(
        "SELECT COUNT(DISTINCT stock_no) FROM tw_backtest_results WHERE run_id=? AND status='ok'",
        (run_id,),
    ).fetchone()[0]
    fail = conn.execute(
        "SELECT COUNT(DISTINCT stock_no) FROM tw_backtest_results WHERE run_id=? AND status!='ok'",
        (run_id,),
    ).fetchone()[0]
    conn.execute(
        "UPDATE tw_backtest_runs SET finished_at=?, ok_count=?, fail_count=? WHERE id=?",
        (time.time(), ok, fail, run_id),
    )
    conn.commit()
    if own:
        conn.close()


def latest_run(conn=None):
    own = conn is None
    conn = conn or connect()
    init_db(conn)
    row = conn.execute("SELECT * FROM tw_backtest_runs ORDER BY id DESC LIMIT 1").fetchone()
    if own:
        conn.close()
    return dict(row) if row else None


def has_stock_result(run_id, stock_no, conn=None):
    own = conn is None
    conn = conn or connect()
    row = conn.execute(
        "SELECT 1 FROM tw_backtest_results WHERE run_id=? AND stock_no=? LIMIT 1",
        (run_id, str(stock_no)),
    ).fetchone()
    if own:
        conn.close()
    return row is not None


def save_stock_results(run_id, stock_no, stock_name, prices, params, results, conn=None):
    own = conn is None
    conn = conn or connect()
    init_db(conn)
    now = time.time()
    price_start = float(prices[0]["close"])
    price_end = float(prices[-1]["close"])
    price_change_pct = (price_end / price_start - 1.0) * 100.0 if price_start else 0.0

    for res in results:
        roi = float(res["roi"])
        buy_hold_roi = float(res["buy_hold_roi"])
        conn.execute("""
        INSERT INTO tw_backtest_results (
            run_id, stock_no, stock_name, status, error, band, months, start_date, end_date,
            days, price_start, price_end, price_change_pct, investment_amount, max_position,
            fee_discount, fee_min, security_type, n_trades, total_fee, total_tax,
            net_invested, peak_invested, final_shares, final_value, profit, roi,
            buy_hold_profit, buy_hold_roi, vs_buy_hold, updated_at
        ) VALUES (
            ?, ?, ?, 'ok', '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """, (
            run_id, str(stock_no), stock_name or "", float(res["band"]), int(params["months"]),
            prices[0]["date"], prices[-1]["date"], len(prices), price_start, price_end,
            price_change_pct, float(params["investment_amount"]), float(params["max_position"]),
            float(params["fee_discount"]), float(params["fee_min"]), params["security_type"],
            int(res["n_trades"]), float(res["total_fee"]), float(res["total_tax"]),
            float(res["net_invested"]), float(res["peak_invested"]), int(res["final_shares"]),
            float(res["final_value"]), float(res["profit"]), roi, float(res["buy_hold_profit"]),
            buy_hold_roi, roi - buy_hold_roi, now,
        ))
    conn.commit()
    if own:
        conn.close()


def save_stock_error(run_id, stock_no, stock_name, params, error, conn=None):
    own = conn is None
    conn = conn or connect()
    init_db(conn)
    conn.execute("""
    INSERT INTO tw_backtest_results (
        run_id, stock_no, stock_name, status, error, months, investment_amount,
        max_position, fee_discount, fee_min, security_type, updated_at
    ) VALUES (?, ?, ?, 'error', ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id, str(stock_no), stock_name or "", str(error), int(params["months"]),
        float(params["investment_amount"]), float(params["max_position"]),
        float(params["fee_discount"]), float(params["fee_min"]), params["security_type"],
        time.time(),
    ))
    conn.commit()
    if own:
        conn.close()


def query_results(run_id=None, q="", band=None, min_roi=None, max_trades=None,
                  status="ok", sort_by="roi", order="desc", limit=100, offset=0,
                  conn=None):
    own = conn is None
    conn = conn or connect()
    init_db(conn)
    if run_id is None:
        run = latest_run(conn)
        run_id = run["id"] if run else None
    if run_id is None:
        if own:
            conn.close()
        return {"run": None, "rows": [], "total": 0}

    clauses = ["run_id = ?"]
    args = [run_id]
    if status:
        clauses.append("status = ?")
        args.append(status)
    if q:
        clauses.append("(stock_no LIKE ? OR stock_name LIKE ?)")
        args.extend([f"%{q}%", f"%{q}%"])
    if band not in (None, ""):
        clauses.append("band = ?")
        args.append(float(band))
    if min_roi not in (None, ""):
        clauses.append("roi >= ?")
        args.append(float(min_roi))
    if max_trades not in (None, ""):
        clauses.append("n_trades <= ?")
        args.append(int(max_trades))

    where_sql = " AND ".join(clauses)
    sort_by = sort_by if sort_by in SORT_COLUMNS else "roi"
    order = "ASC" if str(order).lower() == "asc" else "DESC"
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    total = conn.execute(
        f"SELECT COUNT(*) FROM tw_backtest_results WHERE {where_sql}", args,
    ).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM tw_backtest_results WHERE {where_sql} "
        f"ORDER BY {sort_by} {order}, stock_no ASC LIMIT ? OFFSET ?",
        args + [limit, offset],
    ).fetchall()
    run = conn.execute("SELECT * FROM tw_backtest_runs WHERE id=?", (run_id,)).fetchone()
    if own:
        conn.close()
    return {
        "run": dict(run) if run else None,
        "rows": [dict(r) for r in rows],
        "total": total,
    }
