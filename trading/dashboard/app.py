"""Trading system dashboard - live paper/real account monitor + backtest evidence.

Run with: streamlit run trading/dashboard/app.py
Data updates once per day when scripts/run_paper.py (or run_live.py) executes,
so there is nothing to auto-refresh intraday - reload the page after the daily run.
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.instruments import INSTRUMENTS

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "live_trading.db"

st.set_page_config(page_title="Trading Monitor", layout="wide")
st.title("Trading System — Monitor")
st.caption(
    "Two uncorrelated sleeves, blended 50/50: monthly time-series momentum across 6 micro "
    "futures + daily IBS mean reversion on MES/MNQ (long-only). "
    "Blended backtest: Sharpe 0.92 full-history / 1.27 out-of-sample, max DD -8.9%."
)


def q(conn, sql, params=()):
    return pd.read_sql(sql, conn, params=params)


# ===========================================================================
# LIVE / PAPER ACCOUNT - what you watch day to day
# ===========================================================================
st.header("Account")

if DB_PATH.exists():
    conn = sqlite3.connect(DB_PATH)

    snaps = q(conn, "SELECT * FROM equity_snapshots ORDER BY ts")
    try:
        positions = q(conn, "SELECT * FROM paper_positions ORDER BY symbol")
    except Exception:  # table only exists once the paper broker has run
        positions = pd.DataFrame(columns=["symbol", "contracts", "last_mark_price"])
    orders = q(conn, "SELECT ts, symbol, action, qty, order_type, status, note "
                      "FROM orders ORDER BY ts DESC LIMIT 200")

    if not snaps.empty:
        equity_now = snaps["net_liq"].iloc[-1]
        equity_start = snaps["net_liq"].iloc[0]
        pnl = equity_now - equity_start
        n_fills = int((~orders["status"].isin(["dry_run"])).sum()) if not orders.empty else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Equity", f"${equity_now:,.0f}")
        c2.metric("P&L since start", f"${pnl:+,.0f}", f"{pnl / equity_start:+.2%}")
        c3.metric("Open positions", f"{len(positions)}")
        c4.metric("Orders filled", f"{n_fills}")

        # equity curve of the actual (paper) account
        snaps["ts"] = pd.to_datetime(snaps["ts"])
        fig = go.Figure(go.Scatter(x=snaps["ts"], y=snaps["net_liq"], mode="lines+markers",
                                    line=dict(color="#1565C0")))
        fig.update_layout(height=300, margin=dict(l=10, r=10, t=25, b=10),
                           yaxis_title="Account equity ($)", xaxis_title=None,
                           yaxis_tickformat=",.0f")
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No equity snapshots yet - run `python trading/scripts/run_paper.py` once.")

    left, right = st.columns(2)

    with left:
        st.subheader("Open positions")
        if not positions.empty:
            positions["multiplier"] = positions["symbol"].map(
                {k: v.multiplier for k, v in INSTRUMENTS.items()})
            positions["notional ($)"] = (positions["contracts"].abs()
                                          * positions["last_mark_price"]
                                          * positions["multiplier"])
            positions["side"] = positions["contracts"].apply(lambda c: "LONG" if c > 0 else "SHORT")
            show = positions[["symbol", "side", "contracts", "last_mark_price", "notional ($)"]]
            st.dataframe(show.style.format({"last_mark_price": "{:,.2f}", "notional ($)": "{:,.0f}"}),
                          width="stretch", hide_index=True)
        else:
            st.caption("Flat - no open positions.")

    with right:
        st.subheader("Latest signals")
        tw = q(conn, "SELECT ts, symbol, weight, target_contracts, current_contracts "
                      "FROM target_weights WHERE ts = (SELECT MAX(ts) FROM target_weights) "
                      "ORDER BY symbol")
        if not tw.empty:
            tw["momentum signal"] = tw["weight"].apply(
                lambda x: "long" if x > 0.05 else ("short" if x < -0.05 else "flat"))
            st.dataframe(tw[["symbol", "weight", "momentum signal", "target_contracts"]]
                          .style.format({"weight": "{:+.2f}"}),
                          width="stretch", hide_index=True)
            st.caption(f"As of last run: {tw['ts'].iloc[0]} UTC")
        else:
            st.caption("No signals logged yet.")

    st.subheader("Order history")
    if not orders.empty:
        st.dataframe(orders, width="stretch", hide_index=True)
    else:
        st.caption("No orders yet.")

    conn.close()
else:
    st.info(
        "No trading data yet. Run `python trading/scripts/run_paper.py` for free local "
        "paper trading (no broker account needed), or connect Tradovate and run "
        "`python trading/scripts/run_live.py`."
    )

st.divider()

# ===========================================================================
# BACKTEST EVIDENCE - why these strategies are trusted
# ===========================================================================
st.header("Backtest evidence")

equity_path = DATA_DIR / "momentum_equity_curve.csv"
if equity_path.exists():
    eq = pd.read_csv(equity_path, parse_dates=["date"])
    n_train = int(len(eq) * 0.7)
    train_end_date = eq["date"].iloc[n_train]

    rets = eq["daily_return"].dropna()
    sharpe = (rets.mean() / rets.std()) * (252 ** 0.5) if rets.std() > 0 else 0.0
    running_max = eq["equity_multiple"].cummax()
    max_dd = ((eq["equity_multiple"] - running_max) / running_max).min()
    years = (eq["date"].iloc[-1] - eq["date"].iloc[0]).days / 365.25
    cagr = eq["equity_multiple"].iloc[-1] ** (1 / years) - 1 if years > 0 else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Momentum sleeve Sharpe (25y)", f"{sharpe:.2f}")
    c2.metric("CAGR (unleveraged)", f"{cagr:.1%}")
    c3.metric("Max drawdown", f"{max_dd:.1%}")
    c4.metric("Blend Sharpe (both sleeves)", "0.92")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eq["date"], y=eq["equity_multiple"], name="Equity (x initial)",
                              line=dict(color="#2E7D32")))
    fig.add_vline(x=train_end_date, line_dash="dash", line_color="gray",
                   annotation_text="train/test split", annotation_position="top")
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10),
                       yaxis_title="Equity multiple", xaxis_title=None)
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Momentum sleeve, 25 years. Left of the dashed line = in-sample (parameter selection); "
        "right = out-of-sample (2019-present). The IBS mean-reversion sleeve is validated in "
        "backtest/run_meanrev.py (100% of its parameter grid profitable in train AND test)."
    )
else:
    st.warning("No backtest results found. Run `python trading/backtest/run_momentum.py` first.")
