# Trading system

A backtested, semi-automated futures trading strategy with a dashboard, built to run
against a [Tradovate](https://www.tradovate.com/) account.

## Strategy: diversified time-series momentum

Each of 6 liquid micro futures instruments gets a monthly-rebalanced position:

```
direction = sign(12-month trailing return)
size      = target_volatility / realized_volatility   (per instrument, capped)
```

Instruments: **MES** (S&P 500), **MNQ** (Nasdaq-100), **MCL** (WTI crude), **MGC** (gold),
**SIL** (silver), **M6E** (EUR/USD) - one from each of equities, energy, metals, FX, so the
edge doesn't depend on any single market trending.

This is the "time-series momentum" style documented in
[Moskowitz, Ooi & Pedersen (2012)](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum)
and traded (in more sophisticated forms) by most managed-futures/CTA funds. It works because
it's diversified across uncorrelated macro drivers - a naive single-instrument crossover
strategy on just the S&P 500 was tried first and did **not** show a robust edge (see
"What didn't work" below).

### Backtest results (25 years, ES/NQ/CL/GC/SI/6E daily data via Yahoo, MES/MNQ/MCL/MGC/SIL/M6E
contract economics, includes estimated commissions + slippage)

| Split | Sharpe | CAGR | Max Drawdown |
|---|---|---|---|
| Train (2001-2019) | 0.55 | 3.1% | -13.2% |
| Test / out-of-sample (2019-2026) | 0.80 | 5.1% | -14.1% |
| Full history | 0.63 | 3.7% | -14.1% |

The Sharpe ratio is consistent (0.55-0.81) across the *entire* parameter grid tested
(6-month and 12-month lookback x 8%/10%/12% vol targets) in both train and test periods -
that consistency, not any single number, is what makes this a credible edge rather than
an overfit backtest. Re-run `python backtest/run_momentum.py` to reproduce.

CAGR is on a notional-weighted basis (not accounting for futures margin leverage), so it
understates what's achievable on actual account equity - futures require far less margin
than full notional. Treat CAGR as conservative and Sharpe as the number to trust.

### What didn't work (kept for context, not a bug)

Simple single-instrument trend approaches were tried first and rejected:
- Donchian breakout on ES/NQ: near-zero Sharpe in/out of sample
- EMA(fast)/EMA(slow) crossover on ES/NQ: negative Sharpe

A symmetric long/short strategy on a single equity index fights that index's long-term
upward drift on every short trade. See `backtest/run_search.py` / `data/search_results.csv`
for the full grid search.

## Layout

```
trading/
  data/           historical price CSVs, backtest results, live_trading.db (gitignored)
  strategies/     signal generation (momentum.py is the one actually used)
  backtest/       engine.py (bar-by-bar, used by the rejected single-instrument search)
                  run_momentum.py (the real backtest - run this)
  broker/         tradovate_client.py (REST), paper_broker.py (local sim), trade_log.py
  scripts/        run_paper.py - free local paper trading (start here)
                  run_live.py - Tradovate order routing (needs API subscription)
  dashboard/      app.py - Streamlit dashboard
  config/         settings.py (loads trading/.env), instruments.py (contract specs)
```

## Running it

```bash
pip install -r trading/requirements.txt

# reproduce the backtest
python trading/backtest/run_momentum.py

# paper-trade locally - free, no broker account needed. Run daily or monthly
# (signals only change at month end; daily runs just mark equity to market).
python trading/scripts/run_paper.py

# view the dashboard (backtest + paper/live activity)
streamlit run trading/dashboard/app.py
```

To route orders through a real Tradovate account (demo or live) - which requires
their ~$25/mo API subscription - see
[docs/CONNECT_TRADOVATE.md](../docs/CONNECT_TRADOVATE.md).

### Capital vs. contract granularity

The backtest sizes positions as fractional weights; real trading rounds to whole
contracts. Even micro contracts are chunky (1 MES ≈ $38k notional, 1 MNQ ≈ $59k), so
at the default 10% vol target you need roughly **$250-400k** before all six
instruments can be held simultaneously. With less capital you have two honest
options: raise the vol target (`PAPER_TARGET_VOL=0.15` or `0.20` - same backtested
Sharpe, proportionally deeper drawdowns) or accept that only the strongest signals
produce positions (less diversification than the backtest assumes). The paper trader
prints a warning when most signals are being rounded away.

## Honest caveats

- Backtest uses Yahoo's front-month continuous futures series, which is **not**
  back-adjusted for contract rolls the way a professional data feed would be. Treat
  results as directional evidence of an edge, not a precise P&L forecast.
- Contract multipliers/tick sizes in `config/instruments.py` are from memory of CME
  specs - verify them against Tradovate's contract specs before trusting order sizing
  with real money.
- `scripts/run_live.py` was built and reasoned through carefully but has **not** been
  run against a real Tradovate account (no credentials were available while building
  it). Run it with `DRY_RUN=1` against the demo environment first and sanity-check the
  output before trusting it with `DRY_RUN=0`, and definitely before flipping
  `TRADOVATE_ENV=live`.
- Past performance, including backtested performance, does not guarantee future
  results. A 25-year backtest with a Sharpe of ~0.5-0.75 is a reasonable candidate to
  paper-trade, not a promise.
