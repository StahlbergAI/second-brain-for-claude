"""Short-term mean-reversion signals for equity index futures.

Both rules are long-only: on equity indices, downside overreaction snaps back far more
reliably than upside (shorting strength on an index with upward drift loses money -
the same drift problem that killed the symmetric single-instrument trend strategies,
see backtest/run_search.py).

Convention matches strategies/momentum.py: returned weights[t] = position held DURING
day t, i.e. the signal computed at close of day t-1. Consumers must not shift again.
"""
import pandas as pd


def ibs_state(df: pd.DataFrame, entry: float = 0.2, exit_: float = 0.8,
              trend_filter: int | None = 200) -> pd.Series:
    """Internal Bar Strength: IBS = (close - low) / (high - low).

    A close near the day's low (IBS < entry) on an equity index tends to bounce;
    hold until a close near the day's high (IBS > exit_). Documented extensively on
    index ETFs/futures since the 1990s.

    Returns the UNSHIFTED long/flat state: state[t] = the position decided at the
    close of day t (i.e. what you should hold overnight into day t+1). Live runners
    use state.iloc[-1]; backtests must use ibs_signal (the shifted version).

    trend_filter: only take entries while close > N-day SMA (None disables).
    """
    rng = (df["high"] - df["low"]).replace(0, pd.NA)
    ibs = ((df["close"] - df["low"]) / rng).astype(float)

    enter = ibs < entry
    leave = ibs > exit_
    if trend_filter:
        enter &= df["close"] > df["close"].rolling(trend_filter).mean()

    # forward-fill a long/flat state machine: 1 after an entry bar, 0 after an exit bar
    state = pd.Series(pd.NA, index=df.index, dtype="object")
    state[enter] = 1
    state[leave] = 0
    return state.ffill().fillna(0).astype(float)


def ibs_signal(df: pd.DataFrame, entry: float = 0.2, exit_: float = 0.8,
               trend_filter: int | None = 200) -> pd.Series:
    """Backtest version of ibs_state: weights[t] = position held DURING day t."""
    return ibs_state(df, entry, exit_, trend_filter).shift(1).fillna(0.0)


def pullback_signal(df: pd.DataFrame, entry_low: int = 5, exit_ma: int = 5,
                    trend_filter: int | None = 200) -> pd.Series:
    """Buy a close below the prior N-day low (a sharp pullback) while above the
    long-term trend; exit on a close back above the short moving average."""
    close = df["close"]
    enter = close < df["low"].rolling(entry_low).min().shift(1)
    leave = close > close.rolling(exit_ma).mean()
    if trend_filter:
        enter &= close > close.rolling(trend_filter).mean()

    state = pd.Series(pd.NA, index=df.index, dtype="object")
    state[enter] = 1
    # an entry and exit condition can both be true on the same bar; entry wins
    state[leave & ~enter] = 0
    pos = state.ffill().fillna(0).astype(float)

    return pos.shift(1).fillna(0.0)
