"""RTH / lower-timeframe study - three empirical questions:

1. Where does the return actually accrue: RTH (09:30-16:00) or overnight?
   (literature says overnight; verify on our 730d of hourly data, 8 markets)
2. The published intraday-momentum effect (first 30min -> last 30min), tested
   at our hourly granularity: first hour -> last RTH hour, with real costs.
3. The 15-minute arithmetic: median 15m bar move vs round-trip cost per market
   (60 days of 15m data - the free-data maximum - used ONLY for cost math,
   never for edge claims).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backtest.run_intraday import SPECS, rt_cost_frac

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "intraday"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
YAHOO = {"MES": "ES=F", "MNQ": "NQ=F", "MYM": "YM=F", "M2K": "RTY=F",
         "MGC": "GC=F", "MCL": "CL=F", "M6E": "6E=F", "ZN": "ZN=F"}


def load_hourly(root: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / f"{root.lower()}_1h.csv")
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert("America/New_York")
    df["date"] = df["ts"].dt.date
    df["hour"] = df["ts"].dt.hour
    return df


def sharpe(r: pd.Series) -> float:
    r = r.dropna()
    return (r.mean() / r.std()) * np.sqrt(252) if len(r) > 20 and r.std() > 0 else 0.0


def rth_vs_overnight():
    print("=" * 74)
    print("1) WHERE THE RETURN LIVES (730 trading days, annualized simple mean)")
    print("=" * 74)
    print(f"{'mkt':5s} {'RTH 9:30-16':>12s} {'overnight':>12s} {'RTH Sharpe':>11s} {'o/n Sharpe':>11s}")
    for root in YAHOO:
        d = load_hourly(root)
        opens = d[d["hour"] == 9].set_index("date")["open"]
        closes = d[d["hour"] == 15].set_index("date")["close"]
        idx = opens.index.intersection(closes.index)
        opens, closes = opens.loc[idx], closes.loc[idx]
        rth = (closes / opens - 1)
        overnight = (opens / closes.shift(1) - 1).dropna()
        print(f"{root:5s} {rth.mean() * 252:>11.1%} {overnight.mean() * 252:>11.1%} "
              f"{sharpe(rth):>11.2f} {sharpe(overnight):>11.2f}")


def first_to_last_hour():
    print()
    print("=" * 74)
    print("2) PUBLISHED INTRADAY MOMENTUM, HOURLY ANALOG (first hour -> last hour)")
    print("   long/short the 15:00-16:00 bar in the direction of the 9:00-10:00 bar")
    print("=" * 74)
    rows = []
    for root in YAHOO:
        d = load_hourly(root)
        first = d[d["hour"] == 9].set_index("date")
        last = d[d["hour"] == 15].set_index("date")
        idx = first.index.intersection(last.index)
        sig = np.sign(first.loc[idx, "close"] / first.loc[idx, "open"] - 1)
        raw = (last.loc[idx, "close"] / last.loc[idx, "open"] - 1) * sig
        px = d["close"].median()
        net = raw - rt_cost_frac(root, px)
        rows.append((root, sharpe(raw), sharpe(net), len(raw)))
    print(f"{'mkt':5s} {'gross Sharpe':>13s} {'net Sharpe':>11s} {'n':>5s}")
    for root, g, nn, n in rows:
        print(f"{root:5s} {g:>13.2f} {nn:>11.2f} {n:>5d}")
    port_note = np.mean([g for _, g, _, _ in rows]), np.mean([nn for _, _, nn, _ in rows])
    print(f"avg   {port_note[0]:>13.2f} {port_note[1]:>11.2f}")


def fifteen_min_arithmetic():
    print()
    print("=" * 74)
    print("3) THE 15-MINUTE ARITHMETIC (last 60 days - free-data max for 15m bars)")
    print("   median |close-to-close| move per 15m bar vs round-trip cost")
    print("=" * 74)
    print(f"{'mkt':5s} {'median move':>12s} {'rt cost':>9s} {'cost/move':>10s}  verdict")
    for root, ysym in YAHOO.items():
        try:
            r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{ysym}",
                             params={"range": "60d", "interval": "15m"},
                             headers=HEADERS, timeout=60)
            res = r.json()["chart"]["result"][0]
            closes = pd.Series(res["indicators"]["quote"][0]["close"]).dropna()
        except Exception as exc:
            print(f"{root:5s} fetch failed: {exc}")
            continue
        tick, mult, comm = SPECS[root]
        median_move = closes.diff().abs().median()
        move_usd = median_move * mult
        cost_usd = 2 * tick * mult + comm
        ratio = cost_usd / move_usd if move_usd else np.inf
        verdict = "untradeable" if ratio > 0.5 else ("marginal" if ratio > 0.2 else "workable")
        print(f"{root:5s} {move_usd:>10.2f}$ {cost_usd:>8.2f}$ {ratio:>9.0%}  {verdict}")
    print("\ncost/move = fraction of a typical bar's entire move surrendered per trade.")
    print("For comparison, the DAILY-bar system's ratio on MES is ~2%.")


if __name__ == "__main__":
    rth_vs_overnight()
    first_to_last_hour()
    fifteen_min_arithmetic()
