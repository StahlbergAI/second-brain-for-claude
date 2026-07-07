"""Download historical daily bars for futures continuous contracts from Yahoo Finance.

Yahoo's front-month continuous futures series (e.g. ES=F) is a reasonable free proxy
for backtesting - it is NOT identical to a proper back-adjusted continuous contract
(no roll adjustment), so treat backtest results as directional evidence, not gospel.
"""
import sys
import time
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).parent
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

SYMBOLS = {
    "ES=F": "es_daily.csv",   # E-mini S&P 500
    "NQ=F": "nq_daily.csv",   # E-mini Nasdaq-100
    "MES=F": "mes_daily.csv",  # Micro E-mini S&P 500
    "MNQ=F": "mnq_daily.csv",  # Micro E-mini Nasdaq-100
}


def fetch(symbol: str, range_: str = "25y", interval: str = "1d") -> pd.DataFrame:
    # NOTE: Yahoo silently downgrades interval="1d" to weekly/monthly bars when
    # range="max" is used on futures continuous tickers. A bounded range (<=25y)
    # keeps true daily granularity.
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": range_, "interval": interval, "events": "history"}
    resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    payload = resp.json()["chart"]["result"][0]

    timestamps = payload["timestamp"]
    quote = payload["indicators"]["quote"][0]
    df = pd.DataFrame({
        "date": pd.to_datetime(timestamps, unit="s", utc=True).tz_convert("America/New_York").normalize(),
        "open": quote["open"],
        "high": quote["high"],
        "low": quote["low"],
        "close": quote["close"],
        "volume": quote["volume"],
    })
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    return df


def main():
    for symbol, filename in SYMBOLS.items():
        try:
            df = fetch(symbol)
        except Exception as exc:
            print(f"FAILED {symbol}: {exc}", file=sys.stderr)
            continue
        out_path = DATA_DIR / filename
        df.to_csv(out_path, index=False)
        print(f"{symbol}: {len(df)} rows, {df['date'].min().date()} -> {df['date'].max().date()} -> {out_path}")
        time.sleep(1)


if __name__ == "__main__":
    main()
