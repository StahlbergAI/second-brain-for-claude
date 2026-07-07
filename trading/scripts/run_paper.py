"""Paper-trading runner: the free, no-broker version of run_live.py.

Run this on any schedule (daily is nice for the dashboard's equity curve; monthly is
the minimum since that's when signals change). It:

  1. Refreshes daily prices for the 6-instrument basket (free Yahoo data)
  2. Marks the simulated account to market at the latest close
  3. Recomputes target weights and rebalances the simulated positions
  4. Logs orders / equity / decisions to the same SQLite DB the dashboard reads

No credentials, no subscription, no orders leave your machine.

    python scripts/run_paper.py

Starting equity defaults to $100,000 (override with PAPER_STARTING_EQUITY env var
before the first run - after that, equity evolves with the simulated P&L).

SIZING REALITY CHECK: the backtest sizes in fractional weights, but real accounts
trade whole contracts. One MES contract is ~$38k notional, so on small accounts most
target positions round to zero and you aren't really trading the strategy. Rough
guide: at 10% target vol you want ~$100k+ of (paper) equity; below that, raise
PAPER_TARGET_VOL (e.g. 0.15-0.20 - the backtest grid showed the same Sharpe at
higher vol targets, with proportionally deeper drawdowns).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from broker import paper_broker
from broker.trade_log import log_target_weight
from config.instruments import INSTRUMENTS
from data.fetch_data import fetch, DATA_DIR
from strategies.momentum import compute_signals


def refresh_prices() -> pd.DataFrame:
    series = {}
    for root, inst in INSTRUMENTS.items():
        df = fetch(inst.yahoo_symbol, range_="25y")
        series[root] = df.set_index("date")["close"]
    prices = pd.DataFrame(series).sort_index().dropna()
    prices.to_csv(DATA_DIR / "latest_prices.csv")
    return prices


def main():
    target_vol = float(os.getenv("PAPER_TARGET_VOL", "0.10"))
    prices = refresh_prices()
    weights = compute_signals(prices, lookback_days=252, target_vol=target_vol)
    latest_weights = weights.iloc[-1]
    latest_prices = prices.iloc[-1].to_dict()
    asof = prices.index[-1]
    n = len(INSTRUMENTS)

    equity = paper_broker.mark_to_market(latest_prices)
    print(f"As of {asof.date()}: paper equity after mark-to-market = ${equity:,.2f} "
          f"(target_vol={target_vol:.0%})")

    quantized_away = 0
    for root, inst in INSTRUMENTS.items():
        w = float(latest_weights[root])
        px = float(latest_prices[root])
        notional = (w / n) * equity
        target = int(round(notional / (px * inst.multiplier)))
        if target == 0 and abs(w) > 0.05:
            quantized_away += 1

        delta = paper_broker.rebalance_to(root, target, px)
        log_target_weight(root, w, target, target - delta)
        status = f"traded {delta:+d}" if delta else "no change"
        print(f"  {root}: weight={w:+.2f} price={px:,.2f} target={target:+d} contracts ({status})")

    equity = paper_broker.snapshot_equity()
    print(f"Paper equity after rebalance: ${equity:,.2f}")
    if quantized_away >= n // 2:
        print(f"WARNING: {quantized_away}/{n} non-flat signals rounded to 0 contracts - "
              f"equity is too small for this vol target. Raise PAPER_STARTING_EQUITY "
              f"(fresh DB) or PAPER_TARGET_VOL to trade the strategy meaningfully.")
    print("View the dashboard with: streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
