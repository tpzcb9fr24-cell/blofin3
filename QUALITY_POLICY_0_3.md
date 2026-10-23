# 0.3.0: dollar analytics, experimental risk policy and ETF integration

## What is implemented

- Journal **$ P/L / $100** = 100 × net return on initial position value. Positive and negative values are displayed as dollars. Open paper marks reserve the configured estimated round-trip costs; unavailable marks show UNPRICED.
- Comparison **Avg $ P/L / $100** = the average normalized closed-trade result in the selected asset/time/policy scope. It is not a compounded account result. The comparison now offers All markets or individual-symbol scope.
- Independent quality-v2 paper accounts per strategy track, shared across all five symbols. Account balances use actual modeled quantity × entry value × net return. Show settled and marked equity, open risk, closed-equity dollar drawdown and dollar profit factor. The account $per100 is the marked return scaled to $100 of initial account capital, distinct from per-position $per100. Correlated tracks are never added together.
- New quality-v2 entries: last confirmed structural pivot and signal wick plus 0.25 ATR buffer; reject stops farther than configured stop_pct (default 0.75%); completed 15-minute EMA20 direction/slope filter; opposing-block-capped target must offer at least 1:1 net reward to net stop loss after configured costs. Too little room means skip, never move the target through the block.
- Experimental default paper budgets: $10,000 initial account per strategy, 0.25% settled-equity planned risk per entry, 1% total open planned risk, 0.5% per correlated group, no new entries after 1% of initial capital is lost in a UTC day. SPY/QQQ share one group; BTC/ETH/SOL share another. Position notional is capped by remaining unlevered account capacity. Open positions are not forcibly closed by the daily gate; gaps can exceed planned losses.
- Existing rows migrate to legacy-v1 without rewriting fills/fees. New rows store quality-v2, quantity, estimated cost, and an exact symbol/signal-close/side setup ID. Select a new paper row to list tracks sharing its setup. No retrospective setup IDs are invented for old trades.
- Scrollable rule settings and a local SPY/QQQ market-data setup dialog.

## SPY and QQQ: explicitly pending live acceptance

A Twelve Data **market-data-only key**, with suitable SPY/QQQ entitlement, must be entered in the desktop app. The key is stored using Windows user-bound DPAPI, never in SQLite or a URL, and is not sent to ChatGPT. The adapter permits only read-only time-series/quote market-data endpoints. Redirects are disabled and error messages do not include the key.

ETF bars are regular-session five-minute OHLCV in UTC. The bundled XNYS exchange calendar handles U.S. holidays, daylight-saving changes and early closes. Session gaps are legitimate and missing intraday bars are rejected; no fake overnight/weekend candles are inserted. Polling happens once per five-minute boundary, with a final close reconciliation and no regular overnight polling.

ETF entry prices use the latest timestamped one-minute indicative close, with a maximum timestamp age of 90 seconds. These are **not executable bid/ask quotes**. The provider's daily quote timestamp is not treated as a fresh tick. Missing keys, denied entitlement, rate limits, malformed data, closed sessions, stale signals and delayed prices block new ETF entries. Candle-based exits are conservative stop-first and gap-aware, but do not model executable intrabar quotes. ETF bars are requested with split adjustment.

Genuine Kronos and TimesFM support session-aware inputs and future target timestamps. Kronos's ETF amount is explicitly a close × share-volume proxy, not actual dollar turnover. ETF forecasts are experimental. Synthetic ETF-input inference tests check calendar/model plumbing; they do **not** verify a live ETF feed or predictive accuracy. No live SPY/QQQ key is available to the build runner, so end-to-end ETF live acceptance is BLOCKED until the user configures and verifies access.

## Validation and limitations

The local suite passes 56 tests with one Windows-only protected-key test skipped on Linux. Actual Tk small-window, journal dollar-column, key-dialog, settings-dialog and manual partial-exit/restart checks pass. Windows build observer-6 passed all 57 tests, including protected-key storage, genuine crypto feed/model checks, synthetic ETF-input real inference, frozen GUI, installed desktop and updater tests. The installed/upgraded desktop check observed all three crypto feeds advancing, six model forecasts and manual-journal persistence. The updater retained journal and model hashes. These checks ran on Windows Server 2022, not an interactive Windows 11 desktop.

There is no demonstrated profitability improvement, out-of-sample edge or calibrated forecast confidence. These new thresholds and budgets are engineering hypotheses, not optimized recommendations. Funding, ETF borrow/locate costs, dividends, tax and leverage are excluded. Existing normalized metrics may mix policies only when All policies is selected; the new paper-account tab excludes legacy rows. Annotated SMC/TP agreement and interactive Windows 11 acceptance remain outstanding. Re-run those gates before treating this as a validated trading strategy.

Official references: [Twelve Data](https://twelvedata.com/docs), [U.S. equities data](https://support.twelvedata.com/en/articles/5195429-pre-post-market-data), [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars).

## Verified download

[0.3.0 release](https://github.com/tpzcb9fr24-cell/blofin3/releases/tag/observer-6), source `054b106cfe8a4be0eaa0cbbaea008aa6dfba150f`, [successful Windows run](https://github.com/tpzcb9fr24-cell/blofin3/actions/runs/40014409201). Updater SHA256: `d13768bb3278b9591bc8657340113b73d15a23e036295478b56ec6a58eee2f73`. Full installer SHA256: `7f2dc46b1d4d95df49b5a1117050daca27083c6f83a713228319592daf7304d1`.
