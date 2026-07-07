import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from strategies.momentum import backtest_portfolio, compute_signals

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TRAIN_FRAC = 0.7

INSTRUMENTS = {
    "MES": "es_daily.csv",   # equity index (S&P 500) - proxy for micro contract
    "MNQ": "nq_daily.csv",   # equity index (Nasdaq-100)
    "MCL": "cl_daily.csv",   # energy (WTI crude)
    "MGC": "gc_daily.csv",   # metals (gold)
    "SIL": "si_daily.csv",   # metals (silver)
    "M6E": "e6_daily.csv",   # FX (EUR)
}


def load_prices() -> pd.DataFrame:
    series = {}
    for name, fname in INSTRUMENTS.items():
        df = pd.read_csv(DATA_DIR / fname, parse_dates=["date"])
        df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)
        series[name] = df.set_index("date")["close"]
    prices = pd.DataFrame(series).sort_index()
    prices = prices.dropna()  # keep only dates where all instruments have data
    return prices


def sharpe(returns: pd.Series, periods_per_year: int = 252) -> float:
    r = returns.dropna()
    if len(r) == 0 or r.std() == 0:
        return 0.0
    return (r.mean() / r.std()) * np.sqrt(periods_per_year)


def max_drawdown(equity: pd.Series) -> float:
    running_max = equity.cummax()
    return ((equity - running_max) / running_max).min()


def report(label: str, equity: pd.Series, returns: pd.Series):
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = equity.iloc[-1] ** (1 / years) - 1 if years > 0 else 0.0
    print(f"{label}: Sharpe={sharpe(returns):.2f}  CAGR={cagr:.1%}  "
          f"MaxDD={max_drawdown(equity):.1%}  final={equity.iloc[-1]:.2f}x  years={years:.1f}")


def main():
    prices = load_prices()
    n = int(len(prices) * TRAIN_FRAC)
    train_prices, test_prices = prices.iloc[:n], prices.iloc[n:]

    print(f"Loaded {len(prices)} aligned trading days across {list(INSTRUMENTS)} "
          f"({prices.index.min().date()} -> {prices.index.max().date()})")
    print(f"Train: {train_prices.index.min().date()} -> {train_prices.index.max().date()}")
    print(f"Test:  {test_prices.index.min().date()} -> {test_prices.index.max().date()}\n")

    for lookback in (126, 252):
        for target_vol in (0.08, 0.10, 0.12):
            weights_full = compute_signals(prices, lookback_days=lookback, target_vol=target_vol)
            equity_full, rets_full, _ = backtest_portfolio(prices, weights_full)

            train_equity = equity_full.loc[train_prices.index] / equity_full.loc[train_prices.index].iloc[0]
            test_slice = equity_full.loc[test_prices.index]
            test_equity = test_slice / test_slice.iloc[0]

            train_rets = rets_full.loc[train_prices.index]
            test_rets = rets_full.loc[test_prices.index]

            print(f"lookback={lookback}d target_vol={target_vol:.0%}")
            report("  train", train_equity, train_rets)
            report("  test ", test_equity, test_rets)
            print()

    # final chosen config run on full history for the dashboard / report
    weights = compute_signals(prices, lookback_days=252, target_vol=0.10)
    equity, rets, instrument_rets = backtest_portfolio(prices, weights)
    out = pd.DataFrame({"date": equity.index, "equity_multiple": equity.values, "daily_return": rets.values})
    out.to_csv(DATA_DIR / "momentum_equity_curve.csv", index=False)
    weights.to_csv(DATA_DIR / "momentum_weights.csv")
    print(f"Saved full-history equity curve (lookback=252, target_vol=10%) to "
          f"{DATA_DIR / 'momentum_equity_curve.csv'}")
    report("Full history (252d/10%)", equity / equity.iloc[0], rets)


if __name__ == "__main__":
    main()
