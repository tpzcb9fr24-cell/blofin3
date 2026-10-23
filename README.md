# Alyssa — Multi-market Paper Observer

**0.3.0 candidate: Windows build and installed-app verification pending.** Dollar P/L per $100, independent experimental quality-v2 paper accounts, structure/ATR stops, cost-adjusted reward gates and exposure limits are implemented. Historical trades remain legacy-v1.

**SPY/QQQ live acceptance is BLOCKED pending a user-configured Twelve Data market-data key and ETF entitlement.** The adapter and session-aware model/calendar plumbing are implemented; no live ETF feed or profitability improvement is claimed. See [0.3.0 scope, setup, validation and limitations](QUALITY_POLICY_0_3.md).

[Releases](https://github.com/tpzcb9fr24-cell/blofin3/releases). Close the existing companion before applying an updater. No end-user Python installation or CSV upload. No real order placement or brokerage connection.

## Implemented

- Public BloFin candle5m websocket, heartbeat/reconnect, REST backfill, aligned UTC timestamps, finalized candles, OHLCV validation and SQLite persistence.
- Separate causal SMC Trendline and SMC EMA50 detectors: confirmed pivots, BOS/CHoCH, FVGs, order blocks, relative volume. Independent Fibonacci retracement rejection.
- Separate model confluence tracks for each SMC baseline: +Kronos, +TimesFM and +both; Fibonacci baseline and Fibonacci+SMC+both. These are correlated separate simulations, never a summed portfolio.
- Genuine NeoQuasar/Kronos-small OHLCV/quote-volume inference and tokenizer; genuine Google TimesFM 2.5 200M close-series inference. Up to 512 input bars; six five-minute output steps (30 minutes); separate CPU workers. No substitutes or fabricated outputs on errors. Checkpoints bundled at build time.
- Paper entry crosses fresh bid/ask; fixed stops; opposing-OB TP caps; configurable costs; conservative stop-first ambiguity handling; gap-aware stop fill; no retrospective model fills.
- Per-symbol/time-filtered normalized performance, drawdown/expectancy/R, forecast error scoring against finalized future closes, signal-evidence grid and full EMA/FVG/pivot/Fib overlays.
- Actual-fill local journal with quote prefill, editable UTC time, size, notes, audited entry edits, partial exits, fees, persistence and ±5-minute nearest same-symbol comparison.
- Candlestick chart, active OB and model overlays, live/stale status, comparison table, journal, rules/settings and error log.

## Explicit strategy definitions

These are inspectable engineering assumptions; matching to Alyssa's annotated examples is outstanding.

- Pivots: two bars each side by default, recognized only after right-side confirmation. A close beyond the last unbroken pivot is a structure break; opposite-direction break is CHoCH, continuation is BOS.
- OB: full wick of the last opposite candle within 20 bars before structure break, not previously pierced during origin-to-recognition. Touch/partial mitigation/equality keeps it valid; wick strictly beyond far edge invalidates immediately. New zones are detected from a 512-bar working context. All recognized zones persist in SQLite across rolling context and restarts, including partial touches and first wick invalidation timestamps.
- SMC Trendline: two rising pivot lows / falling pivot highs, retest within 0.1%, matching BOS/CHoCH within ten bars, prior FVG/OB retest, directional rejection, volume confirmation.
- SMC EMA50: trend-side EMA50 close, matching CHoCH within ten bars, prior FVG/OB retest, directional rejection, volume confirmation.
- Fibonacci: latest ordered confirmed swing, 50–61.8% retracement-zone rejection with directional candle and volume. Retracement thresholds and the displayed extension are configurable in settings.
- Volume: prior 20-bar mean × configurable multiplier (default 1). Kronos uses OHLC plus actual base and quote volume. TimesFM uses closes only.
- Model gates: final forecast must agree with direction and use the exact same input-candle timestamp. Entry expires 90 seconds after signal close; no historical forecast is traded at its old input price. Kronos uses one seed-42 sample; no calibrated uncertainty is claimed.
- TP starts at configured R and is capped before the **near wick edge** of the nearest opposing OB, a conservative boundary before the entire zone and its far wick. Long: `OB.low × (1-buffer)`; short: `OB.high × (1+buffer)`. Overlapping/cost-infeasible caps skip. Less than 2R is allowed. The handoff also mentions the far wick; validate this boundary against annotated examples before final strategy acceptance.
- Provisional, unapproved defaults: stop 0.75%, initial 2R, buffer 0.05%, roundtrip costs 0.15%. Displayed spread is crossed; residual slippage/fees are approximated by costs. Funding and leverage are excluded.
- Intrabar entries use subsequent observed prices, not prior candle extremes. Missed intrabar movements cannot be reconstructed precisely.

## Verification and release

`verification/` contains actual live network and genuine model outputs. Unit tests cover parsing, causal pivots, wick validity, target caps, stale forecasts, paper ambiguity/gaps, journal restart/partial exits and observer-only architecture.

The Windows workflow bundles runtime/checkpoints, builds, tests the frozen GUI/models, compiles Inno Setup, silently installs, and exercises the installed binary against live feeds and models. Successful runs publish **prerelease** assets. A Windows Server runner does not prove clean Windows 11 interactive acceptance.

**Outstanding gates:** Windows 11 installed interactive acceptance; annotated strategy/TP validation; outage reconciliation beyond available backfill. The full handoff is not complete while these remain.

## Build-machine only

Python 3.11 x64, CPU torch 2.8.0, `requirements-build.txt`, `scripts/prepare_models.py`, source tests, smoke checks and `.github/workflows/windows-installer.yml`. End users need only the resulting installer. Tested Kronos source revision and checkpoint hashes are retained in the model manifest. Kronos MIT; TimesFM 2.5 Apache-2.0; notices/model cards accompany assets.

Official sources: [BloFin API](https://docs.blofin.com/), [Kronos](https://github.com/shiyu-coder/Kronos), [TimesFM](https://github.com/google-research/timesfm).
