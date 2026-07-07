"""Local paper-trading account: simulates a futures account in SQLite with no broker.

Fills happen at the latest daily close, adjusted by one tick of slippage in the
adverse direction, plus estimated commission. Open positions are settled
mark-to-market on every run (like real futures daily settlement), so equity == cash.

This exists so the whole system can run end-to-end for free - the Tradovate API
subscription is only needed once you want real (demo or live) order routing.
"""
import os
import sqlite3
from contextlib import contextmanager

from broker.trade_log import DB_PATH, log_equity, log_order

from config.instruments import INSTRUMENTS

STARTING_EQUITY = float(os.getenv("PAPER_STARTING_EQUITY", "100000"))

PAPER_SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_meta (
    key TEXT PRIMARY KEY,
    value REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_positions (
    symbol TEXT PRIMARY KEY,
    contracts INTEGER NOT NULL,
    last_mark_price REAL NOT NULL
);

-- cumulative realized+settled P&L per instrument (costs included), for attribution
CREATE TABLE IF NOT EXISTS paper_pnl (
    symbol TEXT PRIMARY KEY,
    cum_pnl REAL NOT NULL DEFAULT 0
);
"""


def _add_pnl(conn, symbol: str, amount: float):
    conn.execute(
        "INSERT INTO paper_pnl (symbol, cum_pnl) VALUES (?, ?) "
        "ON CONFLICT(symbol) DO UPDATE SET cum_pnl = cum_pnl + excluded.cum_pnl",
        (symbol, amount),
    )


@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(PAPER_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_cash(conn) -> float:
    row = conn.execute("SELECT value FROM paper_meta WHERE key='cash'").fetchone()
    if row is None:
        conn.execute("INSERT INTO paper_meta (key, value) VALUES ('cash', ?)", (STARTING_EQUITY,))
        return STARTING_EQUITY
    return row[0]


def set_cash(conn, value: float):
    conn.execute("INSERT OR REPLACE INTO paper_meta (key, value) VALUES ('cash', ?)", (value,))


def get_positions(conn) -> dict[str, tuple[int, float]]:
    rows = conn.execute("SELECT symbol, contracts, last_mark_price FROM paper_positions").fetchall()
    return {sym: (qty, mark) for sym, qty, mark in rows}


def set_position(conn, symbol: str, contracts: int, mark_price: float):
    if contracts == 0:
        conn.execute("DELETE FROM paper_positions WHERE symbol=?", (symbol,))
    else:
        conn.execute(
            "INSERT OR REPLACE INTO paper_positions (symbol, contracts, last_mark_price) VALUES (?, ?, ?)",
            (symbol, contracts, mark_price),
        )


def mark_to_market(latest_prices: dict[str, float]) -> float:
    """Settle all open positions at the latest close. Returns equity after settlement."""
    with _connect() as conn:
        cash = get_cash(conn)
        for symbol, (contracts, last_mark) in get_positions(conn).items():
            px = latest_prices.get(symbol)
            if px is None:
                continue
            spec = INSTRUMENTS[symbol]
            settle = contracts * (px - last_mark) * spec.multiplier
            cash += settle
            _add_pnl(conn, symbol, settle)
            set_position(conn, symbol, contracts, px)
        set_cash(conn, cash)
        return cash


def rebalance_to(symbol: str, target_contracts: int, price: float) -> int:
    """Trade the delta between current and target position, filled at `price` with
    one tick adverse slippage + commission. Returns the delta traded (0 if none)."""
    spec = INSTRUMENTS[symbol]
    with _connect() as conn:
        cash = get_cash(conn)
        current, _ = get_positions(conn).get(symbol, (0, price))
        delta = target_contracts - current
        if delta == 0:
            return 0

        slippage_cost = abs(delta) * spec.tick_size * spec.multiplier
        commission = abs(delta) * spec.commission_rt / 2  # rt estimate / 2 per fill
        cash -= slippage_cost + commission
        _add_pnl(conn, symbol, -(slippage_cost + commission))

        set_position(conn, symbol, target_contracts, price)
        set_cash(conn, cash)

    action = "Buy" if delta > 0 else "Sell"
    log_order(symbol, action, abs(delta), "Market", None, "paper_filled",
              note=f"paper fill @ {price:,.4f}".rstrip("0").rstrip("."))
    return delta


def snapshot_equity() -> float:
    with _connect() as conn:
        cash = get_cash(conn)
    log_equity(None, cash, cash)
    return cash
