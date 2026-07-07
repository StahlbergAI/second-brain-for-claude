"""SQLite trade/equity log shared by the live runner and the dashboard."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "live_trading.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    qty INTEGER NOT NULL,
    order_type TEXT NOT NULL,
    tradovate_order_id INTEGER,
    status TEXT NOT NULL,
    note TEXT
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    account_id INTEGER,
    net_liq REAL,
    cash_balance REAL
);

CREATE TABLE IF NOT EXISTS target_weights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    weight REAL NOT NULL,
    target_contracts INTEGER,
    current_contracts INTEGER
);

-- what each sleeve WANTS (fractional contracts) vs what quantization allows.
-- The gap between ideal and actual is the small-account expression problem,
-- and the dashboard renders it explicitly.
CREATE TABLE IF NOT EXISTS ideal_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    symbol TEXT NOT NULL,
    mom_ideal REAL NOT NULL,
    mr_ideal REAL NOT NULL,
    actual INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT
);
"""


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def log_order(symbol, action, qty, order_type, tradovate_order_id, status, note=""):
    with connect() as conn:
        conn.execute(
            "INSERT INTO orders (ts, symbol, action, qty, order_type, tradovate_order_id, status, note) "
            "VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?)",
            (symbol, action, qty, order_type, tradovate_order_id, status, note),
        )


def log_equity(account_id, net_liq, cash_balance):
    with connect() as conn:
        conn.execute(
            "INSERT INTO equity_snapshots (ts, account_id, net_liq, cash_balance) VALUES (datetime('now'), ?, ?, ?)",
            (account_id, net_liq, cash_balance),
        )


def log_target_weight(symbol, weight, target_contracts, current_contracts):
    with connect() as conn:
        conn.execute(
            "INSERT INTO target_weights (ts, symbol, weight, target_contracts, current_contracts) "
            "VALUES (datetime('now'), ?, ?, ?, ?)",
            (symbol, weight, target_contracts, current_contracts),
        )


def log_ideal_target(symbol, mom_ideal, mr_ideal, actual):
    with connect() as conn:
        conn.execute(
            "INSERT INTO ideal_targets (ts, symbol, mom_ideal, mr_ideal, actual) "
            "VALUES (datetime('now'), ?, ?, ?, ?)",
            (symbol, mom_ideal, mr_ideal, actual),
        )


def log_run(status, message=""):
    with connect() as conn:
        conn.execute("INSERT INTO run_log (ts, status, message) VALUES (datetime('now'), ?, ?)",
                     (status, message))
