"""Diversified time-series momentum (Moskowitz, Ooi & Pedersen 2012 style).

Each instrument's position is: sign(trailing 12-month return) * (target_vol / realized_vol).
Rebalanced monthly, using only information available at the prior month-end close
(no lookahead). Volatility targeting equalizes each instrument's risk contribution so
one asset (e.g. crude oil) doesn't dominate the portfolio's swings.

This is the well-documented, replicated-out-of-sample edge that CTAs trade - it works
because it's diversified across uncorrelated macro drivers (equities, rates, FX, metals,
energy), not because any single market trends reliably on its own.
"""
import numpy as np
import pandas as pd


def month_end_flags(dates: pd.Series) -> pd.Series:
    d = pd.DatetimeIndex(dates)
    is_month_end = d.month != d.to_series().shift(-1).dt.month.to_numpy()
    # The final row always compares against NaT and flags True. That is deliberate:
    # for live use it means "the latest close is a valid signal date", and in backtests
    # a rebalance on the very last bar has no return left to affect.
    return pd.Series(is_month_end, index=dates.index)


def compute_signals(prices: pd.DataFrame, lookback_days: int = 252, vol_lookback: int = 63,
                     target_vol: float = 0.10) -> pd.DataFrame:
    """
    prices: DataFrame indexed by date, one column per instrument (close price).
    Returns a DataFrame of the same shape: position weight per instrument per day,
    updated only at month-end and held constant until the next month-end.
    """
    rets = prices.pct_change()
    momentum = prices.pct_change(lookback_days)
    realized_vol = rets.rolling(vol_lookback).std() * np.sqrt(252)

    raw_weight = np.sign(momentum) * (target_vol / realized_vol.replace(0, np.nan))
    raw_weight = raw_weight.clip(-2.0, 2.0)  # cap leverage per instrument

    is_rebalance = month_end_flags(prices.index.to_series())
    # weights[t] = the position held DURING day t (so it earns day t's return).
    # The shift(1) is what makes this causal: the weight computed from data through
    # month-end close T first applies on day T+1. Consumers must NOT shift again.
    weights = raw_weight.where(is_rebalance).ffill().shift(1)
    return weights.fillna(0.0)


def backtest_portfolio(prices: pd.DataFrame, weights: pd.DataFrame, cost_bps: float = 2.0):
    """
    Equal-risk-budget portfolio: each instrument contributes weight/N of capital.
    cost_bps: round-trip transaction cost in basis points of notional, charged on
    each month's *change* in weight (turnover), to approximate commissions+slippage.
    """
    n_instruments = prices.shape[1]
    rets = prices.pct_change()

    # weights from compute_signals are already lagged (weights[t] = position during
    # day t) - shifting here again would make positions lag their signal by 2 days.
    instrument_rets = weights * rets / n_instruments
    portfolio_ret = instrument_rets.sum(axis=1)

    turnover = (weights - weights.shift(1)).abs().sum(axis=1) / n_instruments
    costs = turnover * (cost_bps / 10_000)
    portfolio_ret_net = portfolio_ret - costs

    equity_curve = (1 + portfolio_ret_net.fillna(0)).cumprod()
    return equity_curve, portfolio_ret_net, instrument_rets
