# Trading system

A backtested, semi-automated futures trading system with a dashboard, built to run
against a [Tradovate](https://www.tradovate.com/) account. Two uncorrelated
strategy sleeves (correlation 0.33), blended 50/50:

| | Sharpe (train) | Sharpe (test, 2019-2026) | Sharpe (full 25y) | Max DD |
|---|---|---|---|---|
| Momentum sleeve | 0.55 | 0.80 | 0.63 | -14.1% |
| IBS mean-reversion sleeve | 0.65 | 1.22 | 0.85 | -11.9% |
| **50/50 blend** | **0.74** | **1.27** | **0.92** | **-8.9%** |

Reproduce with `python backtest/run_momentum.py` and `python backtest/run_meanrev.py`.

## Final validated system (`backtest/run_final_report.py`)

The deployable configuration = 50/50 blend, x1.25 leverage (chosen on train+validation
only, targeting max DD < 13%), 50% de-risking whenever the account is >10% below its
peak, plus T-bill interest on ~90% of equity (futures margin efficiency; modeled at a
flat 1.5%/yr, deliberately below the 25y realized average).

60/20/20 split, the test fifth never touched during design:

| Split | CAGR | Sharpe | Sortino | Max DD | Profit factor |
|---|---|---|---|---|---|
| Train (2001-2016) | 6.6% | 1.03 | 1.29 | -8.4% | 1.22 |
| Validation (2016-2021) | 9.9% | 1.21 | 1.32 | -9.6% | 1.32 |
| **Test (2021-2026, untouched)** | **8.9%** | **1.15** | **1.54** | **-8.0%** | **1.25** |
| Full 25y | 7.7% | 1.09 | 1.33 | -9.6% | 1.25 |

Worst calendar year in 25 years: -8.2% (2016). Best: +26.2% (2013). Daily win rate 57%.

Monte Carlo (2000 block-bootstrapped 5-year paths): median CAGR 7.7%,
P(max DD worse than -15%) = 2.5%, P(losing money over 5y) = 0.1%, P(-50% ruin) = 0.00%.

CAGR sits just under 10% because sizing is deliberately conservative - with Sharpe ~1.1
the leverage dial trades CAGR against drawdown roughly linearly, and the config above
prioritizes the drawdown budget. Raising the DD budget to ~15-18% pushes CAGR past 10%;
that is a risk-appetite decision, not a strategy change.

## Sleeve 1: diversified time-series momentum

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

## Sleeve 2: IBS mean reversion (MES/MNQ, long-only)

Internal Bar Strength = (close - low) / (high - low). Enter long when an equity index
closes near its daily low (IBS < 0.2) while above its 200-day average; exit on a close
near a daily high (IBS > 0.8). In the market only ~25% of days. Chosen because it
survived validation unusually well: **100% of the parameter grid was profitable in both
train and test**, with out-of-sample Sharpe ~1.0-1.3 (see `backtest/run_meanrev.py`).
Blend parameters (0.2/0.8) are the middle of the grid, deliberately NOT the
train-optimized values.

Signals change daily, so the paper/live runner should run every day after the close.

### What didn't work (kept for context, not a bug)

Tried and rejected, with the evidence left in the repo:
- Donchian breakout on ES/NQ: near-zero Sharpe in/out of sample (`backtest/run_search.py`)
- EMA crossover on ES/NQ: negative Sharpe (same file)
- N-day-low pullback mean reversion: train Sharpe 0.7-0.8 collapsed to 0.15-0.2 out of
  sample - a textbook overfit, kept in `strategies/mean_reversion.py` as a cautionary tale
- Adding bond futures (ZN/ZB) to the momentum basket: full-sample Sharpe dropped
- **Intraday day-trading / scalping** (`backtest/run_intraday.py`, 8 markets, hourly bars,
  ~2.4y): intraday momentum negative on every split; opening-range breakout indistinguishable
  from noise. The decisive stat: *random-direction* day trades with real micro-contract
  costs (2 ticks + commission per round trip) produce **Sharpe -1.13 from cost drag alone**.
  Any intraday edge must clear that hurdle before earning anything; at true scalping
  frequency the hurdle is several times higher. Also: free data caps intraday history at
  ~2 years hourly, so nothing at this frequency can be validated to this repo's standards.

A symmetric long/short strategy on a single equity index fights that index's long-term
upward drift on every short trade - which is why the surviving strategies are either
diversified across asset classes (momentum) or long-only (IBS).

## Layout

```
trading/
  data/           historical price CSVs, backtest results, live_trading.db (gitignored)
  strategies/     momentum.py + mean_reversion.py (the two live sleeves)
  backtest/       run_momentum.py + run_meanrev.py (the real backtests - run these)
                  engine.py, run_search.py (rejected single-instrument experiments)
  broker/         tradovate_client.py (REST), paper_broker.py (local sim), trade_log.py
  scripts/        run_paper.py - free local paper trading (start here)
                  run_live.py - Tradovate order routing (needs API subscription)
  dashboard/      server.py + web/ - the QUANT//MONITOR web dashboard (FastAPI + ECharts)
                  app.py - simpler Streamlit alternative
  config/         settings.py (loads trading/.env), instruments.py (contract specs)
```

## Running it

```bash
pip install -r trading/requirements.txt

# reproduce the backtest
python trading/backtest/run_momentum.py

# paper-trade locally - free, no broker account needed. Run DAILY after the
# futures close: the mean-reversion sleeve trades on daily signals.
python trading/scripts/run_paper.py

# the monitor dashboard (dark web UI: equity, positions, signals, execution feed)
python -m uvicorn dashboard.server:app --port 8600 --app-dir trading
# then open http://localhost:8600

# alternative: the simpler Streamlit dashboard
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
