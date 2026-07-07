"""Canonical instrument definitions shared by the backtest, paper broker, and live runner.

Multipliers/ticks are CME micro contract specs. Commissions are typical retail
round-trip estimates - adjust to your actual fee schedule when you go live.
VERIFY these against your broker's contract specs before trading real money.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    root: str            # Tradovate root symbol
    yahoo_symbol: str    # Yahoo Finance continuous-contract ticker used for data
    multiplier: float    # $ per 1.00 move in the quoted price
    tick_size: float     # minimum price increment
    commission_rt: float  # estimated round-trip commission per contract, $


INSTRUMENTS: dict[str, Instrument] = {
    "MES": Instrument("MES", "ES=F", 5, 0.25, 1.50),        # Micro E-mini S&P 500
    "MNQ": Instrument("MNQ", "NQ=F", 2, 0.25, 1.50),        # Micro E-mini Nasdaq-100
    "MCL": Instrument("MCL", "CL=F", 100, 0.01, 1.50),      # Micro WTI Crude
    "MGC": Instrument("MGC", "GC=F", 10, 0.10, 1.50),       # Micro Gold
    "SIL": Instrument("SIL", "SI=F", 1000, 0.005, 2.00),    # Micro Silver (1,000 oz)
    "M6E": Instrument("M6E", "6E=F", 12500, 0.0001, 1.50),  # Micro EUR/USD
}
