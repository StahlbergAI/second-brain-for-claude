"""Validate intraday day-trading strategies on hourly bars, 8 markets, 60/20/20 split.

Costs are charged per round trip per trade as a fraction of notional, using each
contract's real tick value + commission - this is what kills most intraday systems,
so it is modeled explicitly rather than as a generic bps guess.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from strategies.intraday import intraday_momentum, opening_range_breakout

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "intraday"

# root -> (tick_size, $ per point, round-trip commission $)
SPECS = {
    "MES": (0.25, 5, 1.50), "MNQ": (0.25, 2, 1.50), "MYM": (1.0, 0.50, 1.50),
    "M2K": (0.10, 5, 1.50), "MGC": (0.10, 10, 1.50), "MCL": (0.01, 100, 1.50),
    "M6E": (0.0001, 12500, 1.50), "ZN": (0.015625, 1000, 3.00),
}


def rt_cost_frac(root: str, price: float) -> float:
    """Round-trip cost as a fraction of contract notional: 2 ticks slippage + commission."""
    tick, mult, comm = SPECS[root]
    return (2 * tick * mult + comm) / (price * mult)


def sharpe(r: pd.Series) -> float:
    r = r.dropna()
    return (r.mean() / r.std()) * np.sqrt(252) if len(r) > 20 and r.std() > 0 else 0.0


def evaluate(strategy_fn, label: str, **kwargs):
    per_market = {}
    for root in SPECS:
        df = pd.read_csv(DATA_DIR / f"{root.lower()}_1h.csv")
        rets, direction = strategy_fn(df, **kwargs)
        px = pd.read_csv(DATA_DIR / f"{root.lower()}_1h.csv")["close"].median()
        cost = rt_cost_frac(root, px)
        net = rets - (direction != 0) * cost
        per_market[root] = net
    panel = pd.DataFrame(per_market)
    port = panel.mean(axis=1)  # equal-weight across markets, one unit each

    n = len(port)
    tr, va, te = port.iloc[:int(n * .6)], port.iloc[int(n * .6):int(n * .8)], port.iloc[int(n * .8):]
    print(f"\n{label}")
    print(f"  portfolio: train S={sharpe(tr):.2f}  val S={sharpe(va):.2f}  test S={sharpe(te):.2f}  "
          f"(n={n} days, avg {int((panel != 0).sum().sum() / (n or 1))} trades/day across 8 mkts)")
    marks = "  per-market full-period Sharpe: " + "  ".join(
        f"{r}={sharpe(panel[r]):+.2f}" for r in panel)
    print(marks)
    return port, panel


def main():
    print("=" * 70)
    print("INTRADAY STUDY - 8 markets, hourly bars, ~2.4y, flat overnight")
    print("Costs: 2 ticks + commission per round trip, charged on every trade")
    print("=" * 70)

    evaluate(intraday_momentum, "Intraday momentum (trade every day)")
    evaluate(intraday_momentum, "Intraday momentum, 0.15% min first-hour move filter",
             min_move=0.0015)
    evaluate(intraday_momentum, "Intraday momentum, 0.30% filter", min_move=0.003)
    evaluate(opening_range_breakout, "Opening range breakout (10:00 open vs 9-10 range)")

    # randomized-direction benchmark: what Sharpe does pure luck produce here?
    print("\nRandomized-entry benchmark (1000 shuffles of trade direction):")
    df_by_root = {r: pd.read_csv(DATA_DIR / f"{r.lower()}_1h.csv") for r in SPECS}
    rng = np.random.default_rng(7)
    base = {}
    for root, df in df_by_root.items():
        rets, direction = intraday_momentum(df)
        px = df["close"].median()
        base[root] = (rets / direction.replace(0, np.nan)).fillna(0), rt_cost_frac(root, px)
    sharpes = []
    for _ in range(1000):
        cols = {}
        for root, (raw, cost) in base.items():
            d = rng.choice([-1, 1], size=len(raw))
            cols[root] = raw * d - cost
        sharpes.append(sharpe(pd.DataFrame(cols).mean(axis=1)))
    sharpes = np.array(sharpes)
    print(f"  luck distribution: mean {sharpes.mean():.2f}, 95th pct {np.percentile(sharpes, 95):.2f}, "
          f"99th pct {np.percentile(sharpes, 99):.2f}")


if __name__ == "__main__":
    main()
