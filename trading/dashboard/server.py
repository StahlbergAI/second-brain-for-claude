"""FastAPI backend for the trading monitor web dashboard.

Run with:  uvicorn dashboard.server:app --port 8600   (from the trading/ directory)
or:        python -m uvicorn dashboard.server:app --port 8600

Serves the static front-end from dashboard/web/ and JSON APIs over the same
SQLite DB and backtest CSVs the rest of the system writes.
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.instruments import INSTRUMENTS

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "live_trading.db"
WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(title="Trading Monitor API")


def _query(sql: str, params=()) -> list[dict]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.OperationalError:
        return []  # table may not exist yet on a fresh install
    finally:
        conn.close()


@app.get("/api/summary")
def summary():
    snaps = _query("SELECT ts, net_liq FROM equity_snapshots ORDER BY ts")
    positions = _query("SELECT * FROM paper_positions")
    orders = _query("SELECT status FROM orders")
    equity = snaps[-1]["net_liq"] if snaps else None
    start = snaps[0]["net_liq"] if snaps else None
    gross_notional = sum(
        abs(p["contracts"]) * p["last_mark_price"] * INSTRUMENTS[p["symbol"]].multiplier
        for p in positions if p["symbol"] in INSTRUMENTS
    )
    return {
        "equity": equity,
        "pnl": (equity - start) if snaps else None,
        "pnl_pct": (equity / start - 1) if snaps and start else None,
        "open_positions": len(positions),
        "orders_filled": sum(1 for o in orders if o["status"] != "dry_run"),
        "gross_notional": gross_notional,
        "last_update": snaps[-1]["ts"] if snaps else None,
    }


@app.get("/api/equity")
def equity_series():
    return _query("SELECT ts, net_liq FROM equity_snapshots ORDER BY ts")


@app.get("/api/positions")
def positions():
    rows = _query("SELECT symbol, contracts, last_mark_price FROM paper_positions ORDER BY symbol")
    for r in rows:
        inst = INSTRUMENTS.get(r["symbol"])
        r["notional"] = abs(r["contracts"]) * r["last_mark_price"] * (inst.multiplier if inst else 0)
        r["side"] = "LONG" if r["contracts"] > 0 else "SHORT"
    return rows


@app.get("/api/signals")
def signals():
    return _query(
        "SELECT ts, symbol, weight, target_contracts, current_contracts FROM target_weights "
        "WHERE ts = (SELECT MAX(ts) FROM target_weights) ORDER BY symbol")


@app.get("/api/orders")
def orders():
    return _query("SELECT ts, symbol, action, qty, order_type, status, note "
                   "FROM orders ORDER BY ts DESC LIMIT 100")


@app.get("/api/backtest")
def backtest():
    path = DATA_DIR / "momentum_equity_curve.csv"
    if not path.exists():
        return {"curve": [], "stats": None}
    eq = pd.read_csv(path, parse_dates=["date"])
    rets = eq["daily_return"].dropna()
    sharpe = float((rets.mean() / rets.std()) * (252 ** 0.5)) if rets.std() > 0 else 0.0
    running_max = eq["equity_multiple"].cummax()
    max_dd = float(((eq["equity_multiple"] - running_max) / running_max).min())
    years = (eq["date"].iloc[-1] - eq["date"].iloc[0]).days / 365.25
    cagr = float(eq["equity_multiple"].iloc[-1] ** (1 / years) - 1) if years > 0 else 0.0
    n_train = int(len(eq) * 0.7)
    # downsample the curve for the browser (weekly is plenty for 25 years)
    slim = eq.iloc[::5]
    return {
        "curve": [{"date": d.strftime("%Y-%m-%d"), "v": float(v)}
                   for d, v in zip(slim["date"], slim["equity_multiple"])],
        "train_end": eq["date"].iloc[n_train].strftime("%Y-%m-%d"),
        "stats": {"sharpe": sharpe, "cagr": cagr, "max_dd": max_dd,
                   "blend_sharpe": 0.92, "blend_test_sharpe": 1.27, "blend_max_dd": -0.089},
    }


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
