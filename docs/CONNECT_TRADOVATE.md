# Connecting your Tradovate account

> **Cost note:** Tradovate charges a monthly API-access subscription (about **$25/mo**
> as of mid-2026) to issue and use API keys. If you don't want to pay that yet, you
> don't need Tradovate at all - run the strategy with the free local paper trader
> instead: `python trading/scripts/run_paper.py`. Everything below is only for when
> you're ready for real (demo or live) order routing.

## 1. Get a Tradovate account + API access

1. Sign up at [tradovate.com](https://www.tradovate.com/) if you don't have an account.
   A **demo (simulated) account** is free and is what you should use first - do not
   skip straight to live.
2. Log into the Tradovate web/desktop app and go to **Settings → API Access**
   (sometimes labeled "Generate API key"). This self-service flow issues you a
   `cid` (API Client ID) and `sec` (API Secret Key) - separate from your normal
   login password.
3. Full **live** API access generally requires an active API subscription on the
   account. The **demo** environment is normally usable for testing without that, so
   start there regardless of whether you've added the live subscription yet.
4. You now have four pieces of information: your normal Tradovate username/password,
   plus the `cid`/`sec` pair from step 2.

## 2. Configure credentials locally

```bash
cp trading/.env.example trading/.env
```

Edit `trading/.env` and fill in:

```
TRADOVATE_ENV=demo
TRADOVATE_USERNAME=your-tradovate-login
TRADOVATE_PASSWORD=your-tradovate-password
TRADOVATE_CID=the-cid-they-issued-you
TRADOVATE_SEC=the-sec-they-issued-you
```

`trading/.env` is gitignored - it will never be committed. Leave `TRADOVATE_ENV=demo`
until you've watched the system run correctly for a while.

## 3. Verify the connection

```bash
python -c "
import sys; sys.path.insert(0, 'trading')
from broker.tradovate_client import TradovateClient
c = TradovateClient()
c.authenticate()
print(c.list_accounts())
"
```

This should print your (demo) account list. If it errors, double check `.env` and that
your API access has actually been approved by Tradovate.

## 4. Dry-run the strategy

```bash
cd trading
DRY_RUN=1 python scripts/run_live.py
```

This computes the current target portfolio, compares it to your actual account
positions, and **prints** what orders it would place - it does not submit anything.
Inspect the output carefully: target contract counts should be small, sane numbers
(low single digits per instrument for a typical small account), and the resolved
contract symbols (e.g. `MESZ6`) should look like real, current front-month contracts.

## 5. Run for real (on demo first)

```bash
DRY_RUN=0 python scripts/run_live.py
```

With `TRADOVATE_ENV=demo` this places real orders on your *simulated* account. Check
the Tradovate demo platform to confirm fills match expectations, then check the
dashboard (`streamlit run dashboard/app.py`) to confirm the trade log picked it up.

## 6. Automate the monthly rebalance

The strategy only trades once a month (first trading day). On Windows, use Task
Scheduler:

1. Open Task Scheduler → Create Basic Task
2. Trigger: Monthly, day 1 (or "first weekday of month" if available)
3. Action: Start a program
   - Program: `python`
   - Arguments: `scripts\run_live.py`
   - Start in: `C:\Users\stahl\Desktop\second-brain-for-claude\trading`
4. Set the `DRY_RUN` and `TRADOVATE_ENV` environment variables for the task (Task
   Scheduler → task properties, or wrap the call in a `.bat` file that sets them
   before calling python).

## 7. Going live

Only after you're comfortable with demo behavior over a meaningful stretch of time:

1. Set `TRADOVATE_ENV=live` in `trading/.env`
2. Re-verify credentials work against the live endpoint (step 3, same command)
3. Run one more `DRY_RUN=1` pass against live to sanity-check position sizing against
   your *actual* account balance
4. Only then set `DRY_RUN=0` for the scheduled task

Position sizing scales with account net liquidation value automatically (see
`scripts/run_live.py::target_contracts`), so double check your live account balance
before the first live run - the number of contracts traded will differ from demo if the
balances differ.
