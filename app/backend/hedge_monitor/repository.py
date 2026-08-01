import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


PORTFOLIO_FIELDS = (
    "name", "spot_broker", "spot_symbol", "spot_quantity",
    "spot_entry_price", "spot_current_price", "perp_exchange",
    "perp_symbol", "perp_quantity", "perp_entry_price", "perp_mark_price",
    "contract_multiplier", "shares_per_underlying", "usdt_twd",
    "funding_received_usdt", "fees_twd", "enabled",
)

# 通用美元多腿對比（多腿手動、空腿配對 BingX；已實現用手動基準避免換單失真）
USD_LEG_FIELDS = (
    "label", "broker", "quantity", "avg_price", "current_price",
    "pair_exchange", "pair_symbol", "delta_factor", "baseline_realized_usd",
    "entry_date", "note",
)


class HedgeRepository:
    def __init__(self, database_path: str):
        self.database_path = database_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(database_path), exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS hedge_portfolios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    spot_broker TEXT NOT NULL DEFAULT 'sinopac',
                    spot_symbol TEXT NOT NULL,
                    spot_quantity REAL NOT NULL DEFAULT 0,
                    spot_entry_price REAL NOT NULL DEFAULT 0,
                    spot_current_price REAL NOT NULL DEFAULT 0,
                    perp_exchange TEXT NOT NULL DEFAULT 'bingx',
                    perp_symbol TEXT NOT NULL,
                    perp_quantity REAL NOT NULL DEFAULT 0,
                    perp_entry_price REAL NOT NULL DEFAULT 0,
                    perp_mark_price REAL NOT NULL DEFAULT 0,
                    contract_multiplier REAL NOT NULL DEFAULT 1,
                    shares_per_underlying REAL NOT NULL DEFAULT 1,
                    usdt_twd REAL NOT NULL DEFAULT 0,
                    funding_received_usdt REAL NOT NULL DEFAULT 0,
                    fees_twd REAL NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS hedge_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_id INTEGER NOT NULL,
                    captured_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    FOREIGN KEY(portfolio_id) REFERENCES hedge_portfolios(id)
                );
                CREATE INDEX IF NOT EXISTS idx_hedge_snapshots_portfolio_time
                    ON hedge_snapshots(portfolio_id, captured_at);
                CREATE TABLE IF NOT EXISTS usd_hedge_legs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT NOT NULL,
                    broker TEXT,
                    quantity REAL NOT NULL DEFAULT 0,
                    avg_price REAL NOT NULL DEFAULT 0,
                    current_price REAL NOT NULL DEFAULT 0,
                    pair_exchange TEXT NOT NULL DEFAULT 'bingx',
                    pair_symbol TEXT NOT NULL,
                    delta_factor REAL NOT NULL DEFAULT 1,
                    baseline_realized_usd REAL NOT NULL DEFAULT 0,
                    entry_date TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usd_hedge_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    leg_id INTEGER NOT NULL,
                    captured_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    FOREIGN KEY(leg_id) REFERENCES usd_hedge_legs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_usd_hedge_snapshots_leg_time
                    ON usd_hedge_snapshots(leg_id, captured_at);
            """)
            # 針對本 session 稍早已建立、缺 entry_date 欄位的舊資料表做遷移
            existing = {row["name"] for row in connection.execute(
                "PRAGMA table_info(usd_hedge_legs)"
            )}
            if "entry_date" not in existing:
                connection.execute("ALTER TABLE usd_hedge_legs ADD COLUMN entry_date TEXT")
            if "pair_exchange" not in existing:
                # 既有資料都是 BingX 空腿，補上預設值
                connection.execute(
                    "ALTER TABLE usd_hedge_legs ADD COLUMN pair_exchange TEXT "
                    "NOT NULL DEFAULT 'bingx'"
                )

    def list_portfolios(self) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM hedge_portfolios ORDER BY id"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_portfolio(self, portfolio_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM hedge_portfolios WHERE id = ?", (portfolio_id,)
            ).fetchone()
        return dict(row) if row else None

    def save_portfolio(self, data: Dict[str, Any], portfolio_id: int = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        values = {field: data.get(field) for field in PORTFOLIO_FIELDS}
        values["enabled"] = 1 if data.get("enabled", True) else 0
        required = ("name", "spot_symbol", "perp_symbol")
        if any(not values.get(field) for field in required):
            raise ValueError("名稱、現貨代碼與永續合約代碼為必填")

        with self._lock, self._connect() as connection:
            if portfolio_id is None:
                columns = ", ".join(PORTFOLIO_FIELDS)
                placeholders = ", ".join("?" for _ in PORTFOLIO_FIELDS)
                cursor = connection.execute(
                    "INSERT INTO hedge_portfolios ({}, created_at, updated_at) "
                    "VALUES ({}, ?, ?)".format(columns, placeholders),
                    [values[field] for field in PORTFOLIO_FIELDS] + [now, now],
                )
                return int(cursor.lastrowid)

            assignments = ", ".join("{} = ?".format(field) for field in PORTFOLIO_FIELDS)
            cursor = connection.execute(
                "UPDATE hedge_portfolios SET {}, updated_at = ? WHERE id = ?".format(assignments),
                [values[field] for field in PORTFOLIO_FIELDS] + [now, portfolio_id],
            )
            if cursor.rowcount == 0:
                raise KeyError("找不到指定的避險組合")
            return portfolio_id

    def add_snapshot(self, portfolio_id: int, payload: Dict[str, Any]):
        captured_at = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO hedge_snapshots (portfolio_id, captured_at, payload) VALUES (?, ?, ?)",
                (portfolio_id, captured_at, json.dumps(payload, ensure_ascii=False)),
            )

    def list_snapshots(self, portfolio_id: int, limit: int = 100):
        safe_limit = max(1, min(int(limit), 1000))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT captured_at, payload FROM hedge_snapshots "
                "WHERE portfolio_id = ? ORDER BY captured_at DESC LIMIT ?",
                (portfolio_id, safe_limit),
            ).fetchall()
        return [
            {"captured_at": row["captured_at"], **json.loads(row["payload"])}
            for row in rows
        ]

    # ── 通用美元多腿對比 ─────────────────────────────────────────
    def list_usd_legs(self) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM usd_hedge_legs ORDER BY id"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_usd_leg(self, leg_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM usd_hedge_legs WHERE id = ?", (leg_id,)
            ).fetchone()
        return dict(row) if row else None

    def save_usd_leg(self, data: Dict[str, Any], leg_id: int = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        values = {field: data.get(field) for field in USD_LEG_FIELDS}
        if not values.get("label") or not values.get("pair_symbol"):
            raise ValueError("多腿標的與配對 BingX 空腿為必填")
        with self._lock, self._connect() as connection:
            if leg_id is None:
                columns = ", ".join(USD_LEG_FIELDS)
                placeholders = ", ".join("?" for _ in USD_LEG_FIELDS)
                cursor = connection.execute(
                    "INSERT INTO usd_hedge_legs ({}, created_at, updated_at) "
                    "VALUES ({}, ?, ?)".format(columns, placeholders),
                    [values[field] for field in USD_LEG_FIELDS] + [now, now],
                )
                return int(cursor.lastrowid)
            assignments = ", ".join("{} = ?".format(field) for field in USD_LEG_FIELDS)
            cursor = connection.execute(
                "UPDATE usd_hedge_legs SET {}, updated_at = ? WHERE id = ?".format(assignments),
                [values[field] for field in USD_LEG_FIELDS] + [now, leg_id],
            )
            if cursor.rowcount == 0:
                raise KeyError("找不到指定的多腿對比")
            return leg_id

    def delete_usd_leg(self, leg_id: int):
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM usd_hedge_snapshots WHERE leg_id = ?", (leg_id,))
            connection.execute("DELETE FROM usd_hedge_legs WHERE id = ?", (leg_id,))

    def add_usd_snapshot(self, leg_id: int, payload: Dict[str, Any]):
        captured_at = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO usd_hedge_snapshots (leg_id, captured_at, payload) VALUES (?, ?, ?)",
                (leg_id, captured_at, json.dumps(payload, ensure_ascii=False)),
            )

    def list_usd_snapshots(self, leg_id: int, limit: int = 100):
        safe_limit = max(1, min(int(limit), 1000))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT captured_at, payload FROM usd_hedge_snapshots "
                "WHERE leg_id = ? ORDER BY captured_at DESC LIMIT ?",
                (leg_id, safe_limit),
            ).fetchall()
        return [
            {"captured_at": row["captured_at"], **json.loads(row["payload"])}
            for row in rows
        ]
