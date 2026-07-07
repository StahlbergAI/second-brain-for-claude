"""Paper-trading runner: the free, no-broker version of run_live.py.

Trades TWO sleeves (capital split via PAPER_MOM_FRACTION, default 50/50):
  - Diversified time-series momentum (6 instruments, signals change monthly)
  - IBS mean reversion on MES/MNQ (long/flat, signals change daily)

Run this DAILY after the futures close - the mean-reversion sleeve enters and exits
on daily closes, so less-frequent runs miss its trades. It:

  1. Refreshes daily OHLC for the instrument basket (free Yahoo data)
  2. Marks the simulated account to market at the latest close
  3. Recomputes both sleeves' targets and rebalances the simulated positions
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
from strategies.mean_reversion import ibs_state
from strategies.momentum import compute_signals

# Instruments the IBS mean-reversion sleeve trades (equity indices only - the
# bounce-after-weak-close effect is an equity index phenomenon, see run_meanrev.py)
MR_INSTRUMENTS = ("MES", "MNQ")


def refresh_data() -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Full OHLC per instrument - momentum needs closes, mean reversion needs high/low."""
    frames = {}
    for root, inst in INSTRUMENTS.items():
        frames[root] = fetch(inst.yahoo_symbol, range_="25y").set_index("date")
    closes = pd.DataFrame({r: f["close"] for r, f in frames.items()}).sort_index().dropna()
    closes.to_csv(DATA_DIR / "latest_prices.csv")
    return frames, closes


def main():
    target_vol = float(os.getenv("PAPER_TARGET_VOL", "0.10"))
    # capital split between the two sleeves; 50/50 gave the best blend in validation
    # (Sharpe 0.92 full / 1.27 out-of-sample vs 0.63 for momentum alone)
    mom_frac = float(os.getenv("PAPER_MOM_FRACTION", "0.5"))

    frames, prices = refresh_data()
    weights = compute_signals(prices, lookback_days=252, target_vol=target_vol)
    latest_weights = weights.iloc[-1]
    latest_prices = prices.iloc[-1].to_dict()
    asof = prices.index[-1]
    n = len(INSTRUMENTS)

    # mean-reversion sleeve: long/flat state decided at the latest close
    mr_state = {root: float(ibs_state(frames[root]).iloc[-1]) for root in MR_INSTRUMENTS}

    equity = paper_broker.mark_to_market(latest_prices)
    print(f"As of {asof.date()}: paper equity after mark-to-market = ${equity:,.2f} "
          f"(target_vol={target_vol:.0%}, momentum/mean-rev split={mom_frac:.0%}/{1 - mom_frac:.0%})")

    quantized_away = 0
    for root, inst in INSTRUMENTS.items():
        w = float(latest_weights[root])
        px = float(latest_prices[root])
        contract_notional = px * inst.multiplier

        mom_target = (w / n) * mom_frac * equity / contract_notional
        mr_w = mr_state.get(root, 0.0)
        mr_target = (mr_w / len(MR_INSTRUMENTS)) * (1 - mom_frac) * equity / contract_notional
        target = int(round(mom_target + mr_target))
        if target == 0 and (abs(w) > 0.05 or mr_w > 0):
            quantized_away += 1

        delta = paper_broker.rebalance_to(root, target, px)
        log_target_weight(root, w, target, target - delta)
        status = f"traded {delta:+d}" if delta else "no change"
        mr_note = f" mr={mr_w:.0f}" if root in MR_INSTRUMENTS else ""
        print(f"  {root}: mom_weight={w:+.2f}{mr_note} price={px:,.2f} "
              f"target={target:+d} contracts ({status})")

    equity = paper_broker.snapshot_equity()
    print(f"Paper equity after rebalance: ${equity:,.2f}")
    if quantized_away >= n // 2:
        print(f"WARNING: {quantized_away}/{n} non-flat signals rounded to 0 contracts - "
              f"equity is too small for this vol target. Raise PAPER_STARTING_EQUITY "
              f"(fresh DB) or PAPER_TARGET_VOL to trade the strategy meaningfully.")
    print("View the dashboard with: streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
