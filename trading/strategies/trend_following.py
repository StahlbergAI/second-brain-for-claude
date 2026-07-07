"""Candidate trend-following strategies. Each returns (entries, exits, direction) series
aligned to df.index, computed strictly from data available at each bar's close."""
import pandas as pd


def donchian_breakout(df: pd.DataFrame, entry_period: int = 55, exit_period: int = 20):
    """Classic turtle-style breakout: go long on an N-day high, short on an N-day low,
    exit the position on the opposite, shorter-period channel break."""
    high, low, close = df["high"], df["low"], df["close"]

    entry_high = high.rolling(entry_period).max()
    entry_low = low.rolling(entry_period).min()
    exit_high = high.rolling(exit_period).max()
    exit_low = low.rolling(exit_period).min()

    long_entry = close >= entry_high.shift(1)
    short_entry = close <= entry_low.shift(1)
    entries = long_entry | short_entry
    direction = pd.Series(0, index=df.index)
    direction[long_entry] = 1
    direction[short_entry] = -1

    long_exit = close <= exit_low.shift(1)
    short_exit = close >= exit_high.shift(1)
    exits = long_exit | short_exit

    return entries.fillna(False), exits.fillna(False), direction


def ema_crossover(df: pd.DataFrame, fast: int = 20, slow: int = 100):
    """Trade in the direction of a fast/slow EMA crossover; exit (and flip) on the
    opposite crossover. Simpler and more "always in market" than Donchian."""
    close = df["close"]
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()

    bullish = ema_fast > ema_slow
    cross_up = bullish & ~bullish.shift(1).fillna(False)
    cross_down = ~bullish & bullish.shift(1).fillna(False)

    entries = cross_up | cross_down
    direction = pd.Series(0, index=df.index)
    direction[cross_up] = 1
    direction[cross_down] = -1
    exits = entries  # a crossover both closes the old position and opens the new one

    return entries.fillna(False), exits.fillna(False), direction
