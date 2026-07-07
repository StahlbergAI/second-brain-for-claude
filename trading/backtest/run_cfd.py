"""Re-validate the two-sleeve blend under CFD economics (Trade Nation style).

CFDs vs futures - three differences that matter, all modeled here:
  1. Fractional sizing: no whole-contract quantization, so a $5k account can hold
     the exact ideal position. Weight-space backtesting = achievable reality.
  2. Overnight financing: longs pay (benchmark + 2.5%)/yr on notional, daily;
     shorts receive (benchmark - 2.5%)/yr, which is a CHARGE whenever the
     benchmark is below 2.5%. Futures have no such markup, and futures collateral
     earns T-bill yield - CFD margin earns nothing. Both effects included.
  3. Spreads: fixed, wider than futures ticks (US500 1pt, gold 3pt per Trade
     Nation's published schedule; others estimated conservatively - VERIFY).

Sizing is turtle-style percent-of-current-equity throughout (weights scale with
equity by construction), with the same x1.25 leverage and 10%-drawdown de-risking
as the futures final report, so the two reports are directly comparable.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtest.run_final_report import apply_dd_protection, metrics, tbill_daily, FALLBACK_TBILL
from backtest.run_meanrev import load_ohlc
from strategies.mean_reversion import ibs_signal
from strategies.momentum import compute_signals

FINANCING_MARKUP = 0.025   # Trade Nation: interbank +2.5% long / -2.5% short
LEVERAGE = 1.25            # same k as the futures final report

# full quoted spread, in instrument points, charged per round trip.
# US500/XAUUSD are Trade Nation's published fixed spreads; the rest are
# conservative estimates - verify against the platform before going live.
SPREAD_POINTS = {
    "MES": 1.0,     # US500: 1 pt (published)
    "MNQ": 2.0,     # US100: estimate
    "MCL": 0.05,    # WTI: estimate
    "MGC": 3.0,     # XAUUSD: 3 pts (published)
    "SIL": 0.03,    # XAGUSD: estimate (3 cents)
    "M6E": 0.0007,  # EURUSD: estimate (0.7 pip)
}


def rates_series(index: pd.DatetimeIndex) -> pd.Series:
    """Benchmark short rate. FRED if reachable; else a piecewise approximation of
    the Fed funds era structure (labeled clearly in output)."""
    tb = tbill_daily()
    if len(tb):
        return (tb * 252).reindex(index).ffill().fillna(0.018)
    print("NOTE: using piecewise approximate benchmark rates (FRED unreachable).")
    approx = pd.Series(0.018, index=index)
    approx[index < "2008-10-01"] = 0.030
    approx[(index >= "2008-10-01") & (index < "2015-12-01")] = 0.002
    approx[(index >= "2015-12-01") & (index < "2020-03-01")] = 0.015
    approx[(index >= "2020-03-01") & (index < "2022-03-01")] = 0.001
    approx[index >= "2022-03-01"] = 0.045
    return approx


def main():
    files = {"MES": "es_daily.csv", "MNQ": "nq_daily.csv", "MCL": "cl_daily.csv",
             "MGC": "gc_daily.csv", "SIL": "si_daily.csv", "M6E": "e6_daily.csv"}
    ohlc = {k: load_ohlc(f) for k, f in files.items()}
    prices = pd.DataFrame({k: v["close"] for k, v in ohlc.items()}).dropna()
    rets = prices.pct_change()

    # blend exposure per instrument per day (fraction of equity, signed)
    mom_w = compute_signals(prices, lookback_days=252, target_vol=0.10)
    exposure = 0.5 * mom_w / len(files)
    for sym in ("MES", "MNQ"):
        ibs = ibs_signal(ohlc[sym], 0.2, 0.8, 200).reindex(prices.index).fillna(0)
        exposure[sym] = exposure[sym] + 0.5 * ibs / 2

    gross = (exposure * rets).sum(axis=1)

    # spread cost on every exposure change (half spread per side)
    spread_frac = pd.Series({s: SPREAD_POINTS[s] for s in files}) / prices.iloc[-1]
    turnover_cost = (exposure.diff().abs() * (spread_frac / 2)).sum(axis=1)

    # overnight financing on held exposure
    bench = rates_series(prices.index)
    long_exp = exposure.clip(lower=0).sum(axis=1)
    short_exp = (-exposure.clip(upper=0)).sum(axis=1)
    financing = (long_exp * (bench + FINANCING_MARKUP)   # longs always pay
                 - short_exp * (bench - FINANCING_MARKUP)  # shorts: credit iff bench>2.5%
                 ) / 252

    cfd_net = gross - turnover_cost - financing
    cfd_total = apply_dd_protection(cfd_net.dropna(), LEVERAGE)  # no collateral yield on CFD margin

    n = len(cfd_total)
    i_tr, i_va = int(n * 0.6), int(n * 0.8)

    avg_long = long_exp.mean()
    print(f"Average long exposure {avg_long:.2f}x equity, short {short_exp.mean():.2f}x -> "
          f"financing drag at today's ~4.5% benchmark ~ "
          f"{avg_long * (0.045 + FINANCING_MARKUP) * 100:.1f}%/yr of equity")

    print("\n=== CFD SYSTEM (fractional turtle sizing, x1.25, DD protection, NO collateral yield) ===")
    for label, sl in [("TRAIN 60%", cfd_total.iloc[:i_tr]), ("VALIDATION 20%", cfd_total.iloc[i_tr:i_va]),
                       ("TEST 20%", cfd_total.iloc[i_va:]), ("FULL 25y", cfd_total)]:
        m = metrics(sl)
        print(f"\n{label}  ({sl.index[0].date()} -> {sl.index[-1].date()})")
        for key, v in m.items():
            print(f"  {key:14s} {v}")

    # $5k concreteness: what the positions look like in CFD stake terms
    print("\n=== What this means at $5,000 (latest signals, fractional CFD sizes) ===")
    last_exp = exposure.iloc[-1] * LEVERAGE
    for sym in files:
        notional = last_exp[sym] * 5000
        print(f"  {sym}: exposure {last_exp[sym]:+.3f} x equity = ${notional:+,.0f} notional "
              f"(price {prices[sym].iloc[-1]:,.2f})")


if __name__ == "__main__":
    main()
