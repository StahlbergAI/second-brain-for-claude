"""Validate short-term mean reversion on ES/NQ with the same discipline as momentum:
small grid on the train set, chosen config evaluated out-of-sample, and a correlation
check against the momentum strategy (the whole point is diversification - a second
edge only helps if it fires at different times)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from strategies.mean_reversion import ibs_signal, pullback_signal
from strategies.momentum import backtest_portfolio, compute_signals

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TRAIN_FRAC = 0.7
COST_BPS = 3.0  # per unit of turnover; MR trades ~weekly so costs matter more than for momentum


def load_ohlc(fname: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / fname, parse_dates=["date"])
    df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)
    return df.sort_values("date").set_index("date")


def sharpe(r: pd.Series) -> float:
    r = r.dropna()
    return (r.mean() / r.std()) * np.sqrt(252) if len(r) and r.std() > 0 else 0.0


def strat_returns(df: pd.DataFrame, weights: pd.Series) -> pd.Series:
    rets = df["close"].pct_change()
    turnover = weights.diff().abs().fillna(0)
    return weights * rets - turnover * (COST_BPS / 10_000)


def evaluate(df: pd.DataFrame, weights: pd.Series, n_train: int):
    r = strat_returns(df, weights)
    tr, te = r.iloc[:n_train], r.iloc[n_train:]
    exposure = (weights != 0).mean()
    trades = int((weights.diff() > 0).sum())
    return sharpe(tr), sharpe(te), exposure, trades


def main():
    frames = {sym: load_ohlc(f) for sym, f in [("ES", "es_daily.csv"), ("NQ", "nq_daily.csv")]}

    print("=== Grid search (train Sharpe only used for selection) ===")
    results = []
    for sym, df in frames.items():
        n_train = int(len(df) * TRAIN_FRAC)
        for entry in (0.15, 0.20, 0.25):
            for exit_ in (0.75, 0.80, 0.85):
                for tf in (200, None):
                    w = ibs_signal(df, entry, exit_, tf)
                    tr_s, te_s, expo, trades = evaluate(df, w, n_train)
                    results.append((sym, "ibs", dict(entry=entry, exit_=exit_, tf=tf),
                                    tr_s, te_s, expo, trades))
        for el in (5, 10):
            for xm in (5, 10):
                for tf in (200, None):
                    w = pullback_signal(df, el, xm, tf)
                    tr_s, te_s, expo, trades = evaluate(df, w, n_train)
                    results.append((sym, "pullback", dict(entry_low=el, exit_ma=xm, tf=tf),
                                    tr_s, te_s, expo, trades))

    res = pd.DataFrame(results, columns=["sym", "rule", "params", "train_sharpe",
                                          "test_sharpe", "exposure", "n_trades"])

    # selection uses TRAIN only; report the chosen config's TEST result
    print("\n=== Best-per-(symbol,rule) chosen on train, shown with its OOS test Sharpe ===")
    picks = res.loc[res.groupby(["sym", "rule"])["train_sharpe"].idxmax()]
    print(picks.to_string(index=False))

    # robustness: how consistent is the whole grid, not just the winner?
    print("\n=== Grid robustness (share of configs with positive Sharpe) ===")
    for (sym, rule), g in res.groupby(["sym", "rule"]):
        print(f"{sym} {rule}: train {(g.train_sharpe > 0).mean():.0%} positive, "
              f"test {(g.test_sharpe > 0).mean():.0%} positive "
              f"(median test Sharpe {g.test_sharpe.median():.2f})")

    # correlation vs momentum + combined portfolio, using the top train pick overall
    best = picks.sort_values("train_sharpe", ascending=False).iloc[0]
    df = frames[best.sym]
    w = (ibs_signal(df, **{k: v for k, v in best.params.items() if k != "tf"}, trend_filter=best.params["tf"])
         if best.rule == "ibs" else
         pullback_signal(df, best.params["entry_low"], best.params["exit_ma"], best.params["tf"]))
    mr_rets = strat_returns(df, w)

    inst = {"MES": "es_daily.csv", "MNQ": "nq_daily.csv", "MCL": "cl_daily.csv",
            "MGC": "gc_daily.csv", "SIL": "si_daily.csv", "M6E": "e6_daily.csv"}
    prices = pd.DataFrame({k: load_ohlc(f)["close"] for k, f in inst.items()}).dropna()
    mom_w = compute_signals(prices, lookback_days=252, target_vol=0.10)
    _, mom_rets, _ = backtest_portfolio(prices, mom_w)

    joined = pd.concat([mom_rets.rename("mom"), mr_rets.rename("mr")], axis=1).dropna()
    n_train = int(len(joined) * TRAIN_FRAC)
    corr = joined["mom"].corr(joined["mr"])
    combo = 0.7 * joined["mom"] + 0.3 * joined["mr"]

    print(f"\n=== Diversification check (best pick: {best.sym} {best.rule} {best.params}) ===")
    print(f"correlation(momentum, mean-reversion) = {corr:+.2f}")
    print(f"momentum alone   : train Sharpe={sharpe(joined['mom'].iloc[:n_train]):.2f}  "
          f"test Sharpe={sharpe(joined['mom'].iloc[n_train:]):.2f}")
    print(f"mean-rev alone   : train Sharpe={sharpe(joined['mr'].iloc[:n_train]):.2f}  "
          f"test Sharpe={sharpe(joined['mr'].iloc[n_train:]):.2f}")
    print(f"70/30 combination: train Sharpe={sharpe(combo.iloc[:n_train]):.2f}  "
          f"test Sharpe={sharpe(combo.iloc[n_train:]):.2f}")


if __name__ == "__main__":
    main()
