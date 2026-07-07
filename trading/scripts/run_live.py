"""Monthly rebalance runner for the diversified time-series momentum strategy.

Intended to run once per month (see docs/CONNECT_TRADOVATE.md for a Windows Task
Scheduler example) shortly after the futures markets open on the first trading day
of the month. It:

  1. Refreshes daily price history for the 6-instrument basket
  2. Recomputes the latest target portfolio weights (same logic as the backtest)
  3. Pulls current account net liquidation value and open positions from Tradovate
  4. Computes target contract counts per instrument and places orders for the delta
  5. Logs everything to trading/data/live_trading.db for the dashboard

IMPORTANT: This has been reasoned through but NOT run against a live Tradovate
account (no credentials were available while building it). Before scheduling it:
  - Run once manually with TRADOVATE_ENV=demo and DRY_RUN=1, inspect the printed
    target contracts and orders-that-would-be-placed
  - Then run with DRY_RUN=0 against the demo account and confirm fills look right
  - Only then consider TRADOVATE_ENV=live
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from broker.tradovate_client import TradovateClient
from broker.trade_log import log_equity, log_order, log_target_weight
from config.instruments import INSTRUMENTS
from data.fetch_data import fetch, DATA_DIR
from strategies.momentum import compute_signals

DRY_RUN = os.getenv("DRY_RUN", "1") == "1"


def refresh_prices() -> pd.DataFrame:
    series = {}
    for root, inst in INSTRUMENTS.items():
        df = fetch(inst.yahoo_symbol, range_="25y")
        series[root] = df.set_index("date")["close"]
    prices = pd.DataFrame(series).sort_index().dropna()
    prices.to_csv(DATA_DIR / "latest_prices.csv")
    return prices


def target_contracts(root: str, weight: float, net_liq: float, last_price: float) -> int:
    n = len(INSTRUMENTS)
    notional = (weight / n) * net_liq
    contracts = notional / (last_price * INSTRUMENTS[root].multiplier)
    return int(round(contracts))


def current_contracts(positions: list, root: str) -> int:
    total = 0
    for p in positions:
        # Tradovate position `name`/contract symbol starts with the root, e.g. "MESU6"
        if str(p.get("contractName", p.get("name", ""))).startswith(root):
            total += p.get("netPos", 0)
    return total


def main():
    print(f"TRADOVATE_ENV as configured; DRY_RUN={DRY_RUN}")
    prices = refresh_prices()
    weights = compute_signals(prices, lookback_days=252, target_vol=0.10)
    latest_weights = weights.iloc[-1]
    latest_prices = prices.iloc[-1]
    print("Latest target weights:\n", latest_weights)

    client = TradovateClient()
    client.authenticate()
    accounts = client.list_accounts()
    if not accounts:
        raise RuntimeError("No Tradovate accounts returned - check credentials/env.")
    account = accounts[0]
    account_id, account_spec = account["id"], account["name"]

    cash = client.cash_balance(account_id)
    net_liq = cash.get("netLiq") or cash.get("cashBalance") or 0.0
    log_equity(account_id, net_liq, cash.get("cashBalance", 0.0))
    print(f"Account {account_spec} ({account_id}): net_liq={net_liq}")

    positions = client.list_positions()

    for root in INSTRUMENTS:
        w = float(latest_weights[root])
        px = float(latest_prices[root])
        tgt = target_contracts(root, w, net_liq, px)
        cur = current_contracts(positions, root)
        delta = tgt - cur
        log_target_weight(root, w, tgt, cur)
        print(f"{root}: weight={w:+.2f} target={tgt} current={cur} delta={delta}")

        if delta == 0:
            continue

        # NOTE: symbol resolution below is best-effort - verify the returned contract
        # is the intended front/liquid month before relying on this in DRY_RUN=0.
        suggestions = client.suggest_contracts(root, limit=5)
        if not suggestions:
            print(f"  WARNING: no contract found for {root}, skipping order")
            continue
        symbol = suggestions[0]["name"]
        action = "Buy" if delta > 0 else "Sell"
        qty = abs(delta)

        if DRY_RUN:
            print(f"  [DRY RUN] would {action} {qty} {symbol}")
            log_order(symbol, action, qty, "Market", None, "dry_run")
        else:
            result = client.place_order(account_id, account_spec, symbol, action, qty)
            order_id = result.get("orderId")
            print(f"  placed {action} {qty} {symbol} -> orderId={order_id}")
            log_order(symbol, action, qty, "Market", order_id, "submitted")


if __name__ == "__main__":
    main()
