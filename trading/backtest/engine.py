"""Bar-by-bar backtest engine for daily futures strategies.

Design choices (documented because they materially affect results):
- Signals are computed using only data available *at the close* of bar t.
  Entries/exits execute at the *open* of bar t+1 (no lookahead bias).
- Protective stops are checked intrabar using that day's high/low and, if hit,
  fill at the stop price (not the close) - a reasonably conservative assumption.
- Position sizing is volatility-based: risk a fixed fraction of equity per trade,
  sized off the ATR stop distance, rounded down to whole contracts.
- Costs: commission (round-trip, per contract) + slippage (in ticks, per side)
  are subtracted explicitly so results reflect tradeable P&L, not theoretical P&L.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class ContractSpec:
    symbol: str
    multiplier: float       # $ per index point
    tick_size: float         # minimum price increment
    commission_rt: float     # round-trip commission per contract, $
    slippage_ticks: float    # assumed slippage per side, in ticks


CONTRACTS = {
    "ES": ContractSpec("ES", multiplier=50, tick_size=0.25, commission_rt=4.50, slippage_ticks=1),
    "NQ": ContractSpec("NQ", multiplier=20, tick_size=0.25, commission_rt=4.50, slippage_ticks=1),
    "MES": ContractSpec("MES", multiplier=5, tick_size=0.25, commission_rt=1.00, slippage_ticks=1),
    "MNQ": ContractSpec("MNQ", multiplier=2, tick_size=0.25, commission_rt=1.00, slippage_ticks=1),
}


@dataclass
class BacktestConfig:
    initial_capital: float = 50_000.0
    risk_per_trade: float = 0.01   # fraction of equity risked per trade (at the stop)
    max_contracts: int = 20
    atr_stop_mult: float = 3.0     # initial stop distance = atr_stop_mult * ATR
    atr_trail_mult: float = 3.0    # trailing stop distance once in profit (chandelier-style)


@dataclass
class Trade:
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    direction: int          # +1 long, -1 short
    entry_price: float
    exit_price: float
    contracts: int
    pnl: float
    exit_reason: str


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def run_backtest(df: pd.DataFrame, entries: pd.Series, exits: pd.Series, direction: pd.Series,
                  spec: ContractSpec, cfg: BacktestConfig) -> tuple[list[Trade], pd.Series]:
    """
    entries: bool series, True on the bar whose *next* open should open a position
    exits:   bool series, True on the bar whose *next* open should close the position
             (in addition to the engine's own ATR stop/trail logic)
    direction: +1/-1/0, desired direction when entries is True
    """
    df = df.reset_index(drop=True)
    a = atr(df).to_numpy()
    op, hi, lo, cl = df["open"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    dates = df["date"].to_numpy()
    entries_a = entries.to_numpy()
    exits_a = exits.to_numpy()
    dir_a = direction.to_numpy()

    equity = cfg.initial_capital
    equity_curve = np.full(len(df), np.nan)
    equity_curve[0] = equity

    trades: list[Trade] = []
    pos = 0          # contracts, signed
    entry_price = 0.0
    stop_price = 0.0
    entry_date = None

    # Slippage is applied to the fill prices themselves (entry and exit), so the
    # per-contract cost here is commission only - including slippage here too would
    # double-count it.
    cost_per_contract = spec.commission_rt

    for t in range(1, len(df)):
        equity_curve[t] = equity_curve[t - 1]

        if pos != 0:
            # trailing stop (chandelier): only tightens, never loosens, in the trade's favor
            if pos > 0:
                new_stop = hi[t - 1] - cfg.atr_trail_mult * a[t - 1] if not np.isnan(a[t - 1]) else stop_price
                stop_price = max(stop_price, new_stop)
            else:
                new_stop = lo[t - 1] + cfg.atr_trail_mult * a[t - 1] if not np.isnan(a[t - 1]) else stop_price
                stop_price = min(stop_price, new_stop)

            stop_hit = (pos > 0 and lo[t] <= stop_price) or (pos < 0 and hi[t] >= stop_price)
            signal_exit = bool(exits_a[t - 1])

            if stop_hit or signal_exit:
                fill = stop_price if stop_hit else op[t]
                slip = spec.slippage_ticks * spec.tick_size * (1 if pos > 0 else -1)
                fill -= slip
                pnl = (fill - entry_price) * pos * spec.multiplier - cost_per_contract * abs(pos)
                equity += pnl
                equity_curve[t] = equity
                trades.append(Trade(entry_date, dates[t], int(np.sign(pos)), entry_price, fill,
                                     abs(pos), pnl, "stop" if stop_hit else "signal"))
                pos = 0

        if pos == 0 and entries_a[t - 1] and dir_a[t - 1] != 0 and not np.isnan(a[t - 1]) and a[t - 1] > 0:
            d = int(dir_a[t - 1])
            fill = op[t] + spec.slippage_ticks * spec.tick_size * d
            stop_dist = cfg.atr_stop_mult * a[t - 1]
            risk_dollars = equity * cfg.risk_per_trade
            contracts = int(risk_dollars / (stop_dist * spec.multiplier))
            contracts = max(0, min(contracts, cfg.max_contracts))
            if contracts > 0:
                pos = d * contracts
                entry_price = fill
                entry_date = dates[t]
                stop_price = fill - d * stop_dist
                # NOTE: the stop is not evaluated against this entry bar's range;
                # with a 3xATR initial stop on daily bars this is rarely reachable
                # on the entry day, but it is a (slightly optimistic) simplification.

        # mark open positions to market so the equity curve (and Sharpe/drawdown
        # computed from it) reflects unrealized P&L, not just realized trade P&L
        if pos != 0:
            equity_curve[t] = equity + (cl[t] - entry_price) * pos * spec.multiplier

    equity_curve = pd.Series(equity_curve, index=df["date"])
    return trades, equity_curve


def performance_metrics(equity_curve: pd.Series, trades: list[Trade], periods_per_year: int = 252) -> dict:
    returns = equity_curve.pct_change().dropna()
    if len(returns) == 0 or returns.std() == 0:
        sharpe = 0.0
    else:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(periods_per_year)

    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max
    max_dd = drawdown.min()

    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades) if trades else 0.0
    profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else float("inf")
    total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1 if len(equity_curve) else 0.0
    years = (equity_curve.index[-1] - equity_curve.index[0]).days / 365.25 if len(equity_curve) > 1 else 1
    cagr = (equity_curve.iloc[-1] / equity_curve.iloc[0]) ** (1 / years) - 1 if years > 0 else 0.0

    return {
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_return": total_return,
        "cagr": cagr,
        "num_trades": len(trades),
        "final_equity": equity_curve.iloc[-1],
    }
