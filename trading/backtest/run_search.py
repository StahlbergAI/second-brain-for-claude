"""Grid-search candidate strategies on ES and NQ daily data, in-sample (train) then
validate the best params out-of-sample (test), to avoid picking an overfit parameter set."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtest.engine import BacktestConfig, CONTRACTS, performance_metrics, run_backtest
from strategies.trend_following import donchian_breakout, ema_crossover

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TRAIN_FRAC = 0.7

STRATEGIES = {
    "donchian": {
        "fn": donchian_breakout,
        "grid": [
            {"entry_period": ep, "exit_period": xp}
            for ep in (20, 40, 55, 80, 100)
            for xp in (10, 20, 30)
            if xp < ep
        ],
    },
    "ema_cross": {
        "fn": ema_crossover,
        "grid": [
            {"fast": f, "slow": s}
            for f in (10, 20, 30, 50)
            for s in (50, 100, 150, 200)
            if f < s
        ],
    },
}


def load(symbol_file: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / symbol_file, parse_dates=["date"])
    df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)
    return df.sort_values("date").reset_index(drop=True)


def split(df: pd.DataFrame):
    n = int(len(df) * TRAIN_FRAC)
    return df.iloc[:n].reset_index(drop=True), df.iloc[n:].reset_index(drop=True)


def evaluate(df: pd.DataFrame, strat_fn, params: dict, contract: str, cfg: BacktestConfig):
    entries, exits, direction = strat_fn(df, **params)
    spec = CONTRACTS[contract]
    trades, equity_curve = run_backtest(df, entries, exits, direction, spec, cfg)
    metrics = performance_metrics(equity_curve, trades)
    return metrics, trades, equity_curve


def main():
    cfg = BacktestConfig()
    results = []

    # Backtest using the long ES/NQ price history (25y) but size positions with
    # MES/MNQ contract economics ($5 / $2 per point) - a $50k-$100k retail account
    # cannot realistically hold full-size ES/NQ contracts through a 3xATR stop,
    # and MES/MNQ only have ~7y of listed history so can't be used for the price series.
    for symbol_file, contract in [("es_daily.csv", "MES"), ("nq_daily.csv", "MNQ")]:
        df = load(symbol_file)
        train, test = split(df)

        for strat_name, spec in STRATEGIES.items():
            best = None
            for params in spec["grid"]:
                m, _, _ = evaluate(train, spec["fn"], params, contract, cfg)
                if m["num_trades"] < 15:
                    continue
                if best is None or m["sharpe"] > best[0]["sharpe"]:
                    best = (m, params)

            if best is None:
                continue
            train_metrics, best_params = best
            test_metrics, test_trades, test_equity = evaluate(test, spec["fn"], best_params, contract, cfg)
            full_metrics, full_trades, full_equity = evaluate(df, spec["fn"], best_params, contract, cfg)

            results.append({
                "symbol": contract,
                "strategy": strat_name,
                "params": best_params,
                "train_sharpe": train_metrics["sharpe"],
                "test_sharpe": test_metrics["sharpe"],
                "test_cagr": test_metrics["cagr"],
                "test_max_dd": test_metrics["max_drawdown"],
                "test_win_rate": test_metrics["win_rate"],
                "test_trades": test_metrics["num_trades"],
                "full_sharpe": full_metrics["sharpe"],
                "full_cagr": full_metrics["cagr"],
                "full_max_dd": full_metrics["max_drawdown"],
            })

            print(f"{contract} {strat_name}: best_params={best_params}")
            print(f"  train Sharpe={train_metrics['sharpe']:.2f}  "
                  f"test Sharpe={test_metrics['sharpe']:.2f} CAGR={test_metrics['cagr']:.1%} "
                  f"maxDD={test_metrics['max_drawdown']:.1%} win_rate={test_metrics['win_rate']:.1%} "
                  f"trades={test_metrics['num_trades']}")
            print(f"  full-history Sharpe={full_metrics['sharpe']:.2f} CAGR={full_metrics['cagr']:.1%} "
                  f"maxDD={full_metrics['max_drawdown']:.1%}")

    results_df = pd.DataFrame(results).sort_values("test_sharpe", ascending=False)
    out_path = Path(__file__).resolve().parents[1] / "data" / "search_results.csv"
    results_df.to_csv(out_path, index=False)
    print(f"\nSaved ranked results to {out_path}")
    print(results_df.to_string(index=False))


if __name__ == "__main__":
    main()
