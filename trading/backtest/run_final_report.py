"""Final validation report for the two-sleeve blend, per the professional-grade spec:

- 60/20/20 train/validation/test split (leverage chosen on train+val ONLY)
- Collateral yield: futures margin uses ~10-15% of equity; the rest earns T-bill
  interest (3M yield from FRED, the real historical series, not an assumption)
- Drawdown protection: position scale halved while equity is >10% below its peak
- Full metrics: CAGR, Sharpe, Sortino, max/avg drawdown, win rate, profit factor,
  expectancy, best/worst year
- Monte Carlo (block bootstrap) risk-of-ruin analysis
"""
import sys
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtest.run_meanrev import load_ohlc, strat_returns
from strategies.mean_reversion import ibs_signal
from strategies.momentum import backtest_portfolio, compute_signals

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
CASH_FRACTION = 0.90   # share of equity earning T-bill yield (rest is margin)
DD_TRIGGER = 0.10      # drawdown protection kicks in beyond this
DD_SCALE = 0.5         # ...and halves position size
MAX_DD_BUDGET = 0.13   # leverage is chosen so train+val max DD stays under this


def tbill_daily() -> pd.Series:
    """3M T-bill yield from FRED as a daily return series. Falls back to a flat,
    deliberately conservative 1.5%/yr (below the 2001-2026 average) if FRED is
    unreachable, so the report still runs offline."""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS3MO"
    try:
        csv = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"}).text
        df = pd.read_csv(StringIO(csv), na_values=".")
        df.columns = ["date", "yield"]
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")["yield"].ffill() / 100 / 252
    except Exception as exc:
        print(f"NOTE: FRED unreachable ({type(exc).__name__}) - using flat 1.5%/yr "
              "collateral yield, conservative vs the 2001-2026 realized average.")
        return pd.Series(dtype=float)  # empty -> caller fills with constant


FALLBACK_TBILL = 0.015 / 252


def apply_dd_protection(rets: pd.Series, scale: float) -> pd.Series:
    """Scale returns by `scale`, halving exposure while in a >10% drawdown."""
    out = np.zeros(len(rets))
    equity, peak = 1.0, 1.0
    r = rets.to_numpy()
    for i in range(len(r)):
        mult = scale * (DD_SCALE if equity / peak - 1 < -DD_TRIGGER else 1.0)
        out[i] = r[i] * mult
        equity *= 1 + out[i]
        peak = max(peak, equity)
    return pd.Series(out, index=rets.index)


def metrics(rets: pd.Series) -> dict:
    eq = (1 + rets).cumprod()
    years = (rets.index[-1] - rets.index[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / years) - 1
    sharpe = rets.mean() / rets.std() * np.sqrt(252)
    downside = rets[rets < 0].std()
    sortino = rets.mean() / downside * np.sqrt(252) if downside > 0 else np.inf
    peak = eq.cummax()
    dd = eq / peak - 1
    yearly = rets.groupby(rets.index.year).apply(lambda x: (1 + x).prod() - 1)
    active = rets[rets != 0]
    wins, losses = active[active > 0], active[active < 0]
    pf = wins.sum() / -losses.sum() if len(losses) else np.inf
    return {
        "CAGR": f"{cagr:.1%}", "Sharpe": f"{sharpe:.2f}", "Sortino": f"{sortino:.2f}",
        "MaxDD": f"{dd.min():.1%}", "AvgDD": f"{dd[dd < 0].mean():.1%}",
        "BestYr": f"{yearly.max():.1%} ({yearly.idxmax()})",
        "WorstYr": f"{yearly.min():.1%} ({yearly.idxmin()})",
        "WinRate(days)": f"{(active > 0).mean():.0%}",
        "ProfitFactor": f"{pf:.2f}",
        "Expectancy/day": f"{active.mean():.4%}",
    }


def main():
    es, nq = load_ohlc("es_daily.csv"), load_ohlc("nq_daily.csv")
    mr = pd.concat([strat_returns(es, ibs_signal(es, 0.2, 0.8, 200)),
                    strat_returns(nq, ibs_signal(nq, 0.2, 0.8, 200))],
                   axis=1, sort=False).mean(axis=1)
    inst = {"MES": "es_daily.csv", "MNQ": "nq_daily.csv", "MCL": "cl_daily.csv",
            "MGC": "gc_daily.csv", "SIL": "si_daily.csv", "M6E": "e6_daily.csv"}
    prices = pd.DataFrame({k: load_ohlc(f)["close"] for k, f in inst.items()}).dropna()
    mom_w = compute_signals(prices, lookback_days=252, target_vol=0.10)
    _, mom, _ = backtest_portfolio(prices, mom_w)
    blend = (0.5 * mom.rename("m").to_frame().join(mr.rename("r"), how="inner")["m"]
             + 0.5 * mr.reindex(mom.index).dropna())
    blend = blend.dropna()

    n = len(blend)
    i_tr, i_va = int(n * 0.6), int(n * 0.8)

    # choose leverage on train+val ONLY: largest k whose train+val maxDD < budget
    trval = blend.iloc[:i_va]
    ks = np.arange(1.0, 6.01, 0.25)
    k = 1.0
    for cand in ks:
        eq = (1 + apply_dd_protection(trval, cand)).cumprod()
        if (eq / eq.cummax() - 1).min() > -MAX_DD_BUDGET:
            k = cand
    print(f"Leverage chosen on train+val only: k={k:.2f} "
          f"(largest scale keeping train+val maxDD under {MAX_DD_BUDGET:.0%} "
          f"with 50% de-risking beyond {DD_TRIGGER:.0%} drawdown)")

    scaled = apply_dd_protection(blend, k)
    tb = tbill_daily()
    tb = (tb.reindex(scaled.index).ffill().fillna(FALLBACK_TBILL) if len(tb)
          else pd.Series(FALLBACK_TBILL, index=scaled.index))
    total = scaled + CASH_FRACTION * tb

    print("\n=== FINAL SYSTEM (blend x leverage + T-bill collateral yield + DD protection) ===")
    for label, sl in [("TRAIN 60%", total.iloc[:i_tr]), ("VALIDATION 20%", total.iloc[i_tr:i_va]),
                       ("TEST 20% (untouched)", total.iloc[i_va:]), ("FULL 25y", total)]:
        m = metrics(sl)
        print(f"\n{label}  ({sl.index[0].date()} -> {sl.index[-1].date()})")
        for key, v in m.items():
            print(f"  {key:14s} {v}")

    # Monte Carlo: 20-day block bootstrap, 2000 x 5-year paths
    print("\n=== MONTE CARLO (2000 block-bootstrapped 5y paths of the full series) ===")
    rng = np.random.default_rng(11)
    r = total.to_numpy()
    block, horizon = 20, 252 * 5
    n_blocks = horizon // block
    stats = {"cagr": [], "maxdd": []}
    for _ in range(2000):
        idx = rng.integers(0, len(r) - block, n_blocks)
        path = np.concatenate([r[i:i + block] for i in idx])
        eq = np.cumprod(1 + path)
        stats["cagr"].append(eq[-1] ** (1 / 5) - 1)
        peak = np.maximum.accumulate(eq)
        stats["maxdd"].append((eq / peak - 1).min())
    cagr, mdd = np.array(stats["cagr"]), np.array(stats["maxdd"])
    print(f"  CAGR:  median {np.median(cagr):.1%}, 5th pct {np.percentile(cagr, 5):.1%}, "
          f"95th pct {np.percentile(cagr, 95):.1%}")
    print(f"  MaxDD: median {np.median(mdd):.1%}, 5th pct (worst) {np.percentile(mdd, 5):.1%}")
    print(f"  P(5y max drawdown worse than -15%): {(mdd < -0.15).mean():.1%}")
    print(f"  P(5y max drawdown worse than -25%): {(mdd < -0.25).mean():.1%}")
    print(f"  P(losing money over 5y): {(cagr < 0).mean():.1%}")
    print(f"  P(ruin, -50%): {(mdd < -0.50).mean():.2%}")


if __name__ == "__main__":
    main()
