"""Intraday (day-trading) strategies on hourly futures bars. Always flat overnight.

Uniform session template across all markets (deliberately NOT tuned per market):
  signal bar : 09:00-10:00 NY (captures the 09:30 equity open)
  entry      : 10:00 bar open
  exit       : 15:00 bar close (~16:00, end of day session)

Two documented effects:
- Intraday time-series momentum: the first hour's direction tends to persist into
  the close (Gao, Han, Li & Zhou 2018, "Market intraday momentum").
- Opening range breakout: a close beyond the first hour's range tends to continue.
"""
import pandas as pd

SIGNAL_HOUR = 9
ENTRY_HOUR = 10
EXIT_HOUR = 15


def _sessions(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot hourly bars into one row per NY trading date with the bars we need."""
    d = df.copy()
    d["ts"] = pd.to_datetime(d["ts"], utc=True).dt.tz_convert("America/New_York")
    d["date"] = d["ts"].dt.date
    d["hour"] = d["ts"].dt.hour

    sig = d[d["hour"] == SIGNAL_HOUR].set_index("date")
    entry = d[d["hour"] == ENTRY_HOUR].set_index("date")
    ex = d[d["hour"] == EXIT_HOUR].set_index("date")

    out = pd.DataFrame({
        "sig_open": sig["open"], "sig_high": sig["high"],
        "sig_low": sig["low"], "sig_close": sig["close"],
        "entry_open": entry["open"],
        "exit_close": ex["close"],
    }).dropna()
    out.index = pd.to_datetime(out.index)
    return out


def intraday_momentum(df: pd.DataFrame, min_move: float = 0.0) -> pd.Series:
    """Direction = sign of the signal bar's return; hold entry->close same day.
    min_move: only trade if |first-hour return| exceeds this (filters chop)."""
    s = _sessions(df)
    r1 = s["sig_close"] / s["sig_open"] - 1
    direction = r1.apply(lambda x: 1 if x > min_move else (-1 if x < -min_move else 0))
    day_ret = (s["exit_close"] / s["entry_open"] - 1) * direction
    day_ret.name = "ret"
    return day_ret, direction


def opening_range_breakout(df: pd.DataFrame) -> pd.Series:
    """Long if the entry bar opens above the signal bar's high, short below its low.
    (With hourly bars the 'breakout' check is the 10:00 open vs the 9-10 range.)"""
    s = _sessions(df)
    direction = pd.Series(0, index=s.index)
    direction[s["entry_open"] > s["sig_high"]] = 1
    direction[s["entry_open"] < s["sig_low"]] = -1
    day_ret = (s["exit_close"] / s["entry_open"] - 1) * direction
    day_ret.name = "ret"
    return day_ret, direction
