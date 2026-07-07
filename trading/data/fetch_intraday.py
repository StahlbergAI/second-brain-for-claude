"""Fetch ~2 years of hourly OHLCV futures bars from Yahoo into data/intraday/.

Yahoo caps hourly history at 730 days - that is the honest limit of free intraday
data. Sufficient for a preliminary study across 8 markets; NOT sufficient for the
10-year multi-regime validation a production intraday system deserves.
"""
import sys
import time
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).parent / "intraday"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

SYMBOLS = {
    "MES": "ES=F", "MNQ": "NQ=F", "MYM": "YM=F", "M2K": "RTY=F",
    "MGC": "GC=F", "MCL": "CL=F", "M6E": "6E=F", "ZN": "ZN=F",
}


def fetch_hourly(yahoo_symbol: str) -> pd.DataFrame:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
    params = {"range": "730d", "interval": "1h"}
    resp = requests.get(url, params=params, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    payload = resp.json()["chart"]["result"][0]
    quote = payload["indicators"]["quote"][0]
    df = pd.DataFrame({
        "ts": pd.to_datetime(payload["timestamp"], unit="s", utc=True).tz_convert("America/New_York"),
        "open": quote["open"], "high": quote["high"], "low": quote["low"],
        "close": quote["close"], "volume": quote["volume"],
    }).dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    return df


def main():
    DATA_DIR.mkdir(exist_ok=True)
    for root, ysym in SYMBOLS.items():
        try:
            df = fetch_hourly(ysym)
        except Exception as exc:
            print(f"FAILED {root}: {exc}", file=sys.stderr)
            continue
        out = DATA_DIR / f"{root.lower()}_1h.csv"
        df.to_csv(out, index=False)
        print(f"{root}: {len(df)} bars {df['ts'].iloc[0]} -> {df['ts'].iloc[-1]}")
        time.sleep(1)


if __name__ == "__main__":
    main()
