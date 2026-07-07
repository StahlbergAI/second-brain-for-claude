"""Streamlit dashboard: backtest results + (once running) live paper/demo trading log.

Run with: streamlit run trading/dashboard/app.py
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "live_trading.db"

st.set_page_config(page_title="Trading Strategy Dashboard", layout="wide")
st.title("Trading System — Dashboard")

st.caption(
    "Two uncorrelated sleeves, blended 50/50: (1) monthly-rebalanced time-series momentum "
    "across MES, MNQ, MCL, MGC, SIL, M6E micro futures, vol-targeted; (2) daily IBS "
    "mean reversion on MES/MNQ, long-only. Backtest chart below shows the momentum sleeve; "
    "blended results: Sharpe 0.92 full-history / 1.27 out-of-sample, max drawdown -8.9%."
)

# ---------------------------------------------------------------------------
# Backtest section
# ---------------------------------------------------------------------------
equity_path = DATA_DIR / "momentum_equity_curve.csv"
if equity_path.exists():
    eq = pd.read_csv(equity_path, parse_dates=["date"])

    n_train = int(len(eq) * 0.7)
    train_end_date = eq["date"].iloc[n_train]

    col1, col2, col3, col4 = st.columns(4)
    rets = eq["daily_return"].dropna()
    sharpe = (rets.mean() / rets.std()) * (252 ** 0.5) if rets.std() > 0 else 0.0
    running_max = eq["equity_multiple"].cummax()
    max_dd = ((eq["equity_multiple"] - running_max) / running_max).min()
    years = (eq["date"].iloc[-1] - eq["date"].iloc[0]).days / 365.25
    cagr = eq["equity_multiple"].iloc[-1] ** (1 / years) - 1 if years > 0 else 0.0

    col1.metric("Backtest Sharpe (25y)", f"{sharpe:.2f}")
    col2.metric("CAGR", f"{cagr:.1%}")
    col3.metric("Max Drawdown", f"{max_dd:.1%}")
    col4.metric("Final equity multiple", f"{eq['equity_multiple'].iloc[-1]:.2f}x")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eq["date"], y=eq["equity_multiple"], name="Equity (x initial)",
                              line=dict(color="#2E7D32")))
    fig.add_vline(x=train_end_date, line_dash="dash", line_color="gray",
                   annotation_text="train/test split", annotation_position="top")
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10),
                       yaxis_title="Equity multiple", xaxis_title="Date")
    st.plotly_chart(fig, width='stretch')
    st.caption(
        "Left of the dashed line = in-sample (parameter selection). Right = out-of-sample "
        "test period (2019-present, includes COVID crash and 2022 rate-hike regime)."
    )
else:
    st.warning("No backtest results found yet. Run `python trading/backtest/run_momentum.py` first.")

st.divider()

# ---------------------------------------------------------------------------
# Latest target weights
# ---------------------------------------------------------------------------
weights_path = DATA_DIR / "momentum_weights.csv"
if weights_path.exists():
    st.subheader("Latest target portfolio weights")
    w = pd.read_csv(weights_path, index_col=0, parse_dates=True)
    latest = w.iloc[-1].rename("weight").to_frame()
    latest["direction"] = latest["weight"].apply(lambda x: "long" if x > 0 else ("short" if x < 0 else "flat"))
    st.dataframe(latest.style.format({"weight": "{:+.2f}"}), width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# Live trading log (populated once scripts/run_live.py has actually run)
# ---------------------------------------------------------------------------
st.subheader("Live / paper trading activity")

if DB_PATH.exists():
    conn = sqlite3.connect(DB_PATH)

    eq_snap = pd.read_sql("SELECT * FROM equity_snapshots ORDER BY ts", conn)
    if not eq_snap.empty:
        st.line_chart(eq_snap.set_index("ts")["net_liq"])
    else:
        st.info("No equity snapshots logged yet.")

    orders = pd.read_sql("SELECT * FROM orders ORDER BY ts DESC LIMIT 100", conn)
    st.write("Recent orders")
    st.dataframe(orders, width='stretch')

    tw = pd.read_sql("SELECT * FROM target_weights ORDER BY ts DESC LIMIT 50", conn)
    st.write("Recent rebalance decisions")
    st.dataframe(tw, width='stretch')

    conn.close()
else:
    st.info(
        "No trading activity yet. Run `python trading/scripts/run_paper.py` for free local "
        "paper trading (no broker account needed), or connect Tradovate and run "
        "`python trading/scripts/run_live.py`."
    )
