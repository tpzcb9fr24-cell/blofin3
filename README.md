# 0.3.2 direction-only paper comparison

**0.3.2 prerelease verified on Windows Server 2022:** 73 tests passed; genuine offline Kronos/TimesFM inference, source/frozen/installed GUI, paired flip ledger/exits/restart, and updater journal/model-preservation checks passed with explicitly synthetic fixtures. Separately, real BloFin REST history, fresh bid/ask and public WebSocket checks PASSED for BTC/ETH/SOL at build time. This is not a profitability result or interactive Windows 11/live ETF acceptance.

[Download 0.3.2 updater](https://github.com/tpzcb9fr24-cell/blofin3/releases/download/observer-9/BloFinObserver-Update.exe) | [Full 0.3.2 installer](https://github.com/tpzcb9fr24-cell/blofin3/releases/download/observer-9/BloFinObserver-Setup.exe) | [Successful build](https://github.com/tpzcb9fr24-cell/blofin3/actions/runs/40316889469).

[Installed/offline test evidence](https://github.com/tpzcb9fr24-cell/blofin3/actions/runs/40316889469/artifacts/12648440417) | [Separate live provider status](https://github.com/tpzcb9fr24-cell/blofin3/actions/runs/40316889469/artifacts/12647630498).

Updater SHA256: `c09e5cddc71c204d6cbccd41a5c289dc55422fdfda1e349f3a588762832f30c0`. Full installer SHA256: `5a0a0867bafd1c72aa2fa664cffdcee05a0daca69c8be7dd302ccafb58023f3b`. Built source: `74c9b714268c4c1f65853c9c8308e591f828748e`. Production confirmation/freshness gates remain unchanged. Offline test fixtures never enter normal startup or the user's journal.

Each accepted new original paper entry attempts a paired `[FLIP]` entry in a separate track: long becomes short; short becomes long. It copies original quantity, entry timestamp, configured costs, stop-distance percentage and target-distance percentage. A 2R plan remains 2R. Crypto uses the opposite side of the same observed bid/ask quote; ETF prices remain indicative. The stop and target distances are mirrored around the flipped fill, never swapped. Models and opposing-order-block target gates still determine the original signal; they are not reapplied in the opposite direction. This is an explicit direction-only experiment, not an alternative SMC detector. The original tracks and old history are retained. Old trades are never backfilled into the live ledger.

The experiment inherits original sizing, not an independently optimized or rebalanced account policy. A previous open flip blocks another entry in the same flipped track/symbol and that skipped pairing is audited. Exits use the same conservative stop-first/gap-aware paper logic. Results can differ in duration; original losses do not imply flipped wins. All activity is paper-only. No profitability claim; Windows 11 interactive and live ETF acceptance remain outstanding.

# 0.3.1 entry diagnostics and bounded quote retry

Windows Server 2022 verification passed: 66 tests, genuine crypto/model checks, source/frozen/installed GUI checks (including the history dialog), and updater journal/model preservation. Interactive Windows 11 and live ETF acceptance remain outstanding.

[Download 0.3.1 updater](https://github.com/tpzcb9fr24-cell/blofin3/releases/download/observer-7/BloFinObserver-Update.exe) | [Full 0.3.1 installer](https://github.com/tpzcb9fr24-cell/blofin3/releases/download/observer-7/BloFinObserver-Setup.exe) | [Successful build](https://github.com/tpzcb9fr24-cell/blofin3/actions/runs/40087761196).

Updater SHA256: `0ac5d3599bf846644efcffb4c84950c6538e5246f69e14d953a09a31c949d40f`. Source: `c8af7d2addacbfa143fd53c747d86b94732a5d5f`.

- Signals & evidence → Decision history — last 12 hours → Copy report.
- Entry outcomes persist in SQLite: waiting for quotes/models, expired, stop/target/risk/model rejection, existing position and opened paper trade. Read-only feed/transport errors persist across restarts.
- Failed fresh-quote requests retry after 5 seconds (60 seconds on HTTP 403), sharing backoff across strategy tracks for the same symbol. All retries use the original 90-second signal expiry. Late-returning quotes never fill after that deadline. No alternate host, geolocation bypass, historical fill or weaker strategy filter is added.
- Legacy decisions without saved execution outcomes remain explicitly UNKNOWN. This update cannot establish why a historical signal had no trade.
- Existing journal, real model files and protected market-data key remain local. Observer-only; never places real orders. SPY/QQQ live verification and Windows 11 interactive acceptance remain outstanding; no profitability claim.

# Alyssa — Multi-market Paper Observer

**0.3.0 prerelease: Windows build, installed-app and updater checks passed on Windows Server 2022.** Dollar P/L per $100, independent experimental quality-v2 paper accounts, structure/ATR stops, cost-adjusted reward gates and exposure limits are implemented. Historical trades remain legacy-v1.

**SPY/QQQ live acceptance is BLOCKED pending a user-configured Twelve Data market-data key and ETF entitlement.** The adapter and session-aware model/calendar plumbing are implemented; no live ETF feed or profitability improvement is claimed. See [0.3.0 scope, setup, validation and limitations](QUALITY_POLICY_0_3.md).

[Download the 0.3.0 updater](https://github.com/tpzcb9fr24-cell/blofin3/releases/download/observer-6/BloFinObserver-Update.exe) for an existing installation, or [full installer](https://github.com/tpzcb9fr24-cell/blofin3/releases/download/observer-6/BloFinObserver-Setup.exe) for a new computer. [Build and verification](https://github.com/tpzcb9fr24-cell/blofin3/actions/runs/40014409201). Close the existing companion before applying an updater. No end-user Python installation or CSV upload. No real order placement or brokerage connection.

## Implemented

- Public BloFin candle5m websocket, heartbeat/reconnect, REST backfill, aligned UTC timestamps, finalized candles, OHLCV validation and SQLite persistence.
- Separate causal SMC Trendline and SMC EMA50 detectors: confirmed pivots, BOS/CHoCH, FVGs, order blocks, relative volume. Independent Fibonacci retracement rejection.
- Separate model confluence tracks for each SMC baseline: +Kronos, +TimesFM and +both; Fibonacci baseline and Fibonacci+SMC+both. These are correlated separate simulations, never a summed portfolio.
- Genuine NeoQuasar/Kronos-small OHLCV/quote-volume inference and tokenizer; genuine Google TimesFM 2.5 200M close-series inference. Up to 512 input bars; six five-minute output steps (30 continuous minutes for crypto; six regular-session bars for ETFs); separate CPU workers. No substitutes or fabricated outputs on errors. Checkpoints bundled at build time.
- Crypto paper entry crosses fresh bid/ask; ETF entry uses a timestamped one-minute indicative close; opposing-OB TP caps; configurable costs; conservative stop-first ambiguity handling; gap-aware stop fill; no retrospective model fills.
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
- Volume: prior 20-bar mean × configurable multiplier (default 1). Kronos uses OHLC plus actual base and quote volume for crypto; ETF amount is a labeled close × share-volume proxy. TimesFM uses closes only.
- Model gates: final forecast must agree with direction and use the exact same input-candle timestamp. Entry expires 90 seconds after signal close; no historical forecast is traded at its old input price. Kronos uses one seed-42 sample; no calibrated uncertainty is claimed.
- TP starts at configured R and is capped before the **near wick edge** of the nearest opposing OB, a conservative boundary before the entire zone and its far wick. Long: `OB.low × (1-buffer)`; short: `OB.high × (1+buffer)`. Overlapping/cost-infeasible caps skip. Legacy rules allow less than 2R; quality-v2 requires at least 1R net of configured costs and skips a capped target without sufficient room. The handoff also mentions the far wick; validate this boundary against annotated examples before final strategy acceptance.
- Experimental quality-v2 defaults: structural/ATR stop limited to 0.75%, initial 2R, target buffer 0.05%, estimated roundtrip costs 0.15% crypto / 0.05% ETFs. Legacy policy uses a fixed 0.75% stop. Crypto spread is crossed; residual costs are approximated. ETF prices are indicative, with no executable bid/ask simulation. Funding, ETF borrow/locate, dividends, taxes and leverage are excluded.
- Intrabar entries use subsequent observed prices, not prior candle extremes. Missed intrabar movements cannot be reconstructed precisely.

## Verification and release

The successful [build evidence artifact](https://github.com/tpzcb9fr24-cell/blofin3/actions/runs/40014409201/artifacts/12528282467) contains current real network/model, GUI and installed/upgraded desktop evidence; `verification/` retains earlier outputs. Windows: **57 tests passed**. Local Linux: 56 passed, one Windows-only test skipped. Installed/upgraded desktop checks observed advancing BTC/ETH/SOL data, all six genuine model forecasts and a manual journal record surviving restart. Update tests verified unchanged journal and model hashes. Unit tests cover parsing, causal pivots, wick validity, target caps, stale forecasts, paper ambiguity/gaps, journal restart/partial exits and observer-only architecture.

The Windows workflow bundles runtime/checkpoints, builds, tests the frozen GUI/models, compiles Inno Setup, silently installs, and exercises the installed binary against live feeds and models. Successful runs publish **prerelease** assets. A Windows Server runner does not prove clean Windows 11 interactive acceptance.

**Outstanding gates:** Windows 11 installed interactive acceptance; annotated strategy/TP validation; outage reconciliation beyond available backfill. The full handoff is not complete while these remain.

## Build-machine only

Python 3.11 x64, CPU torch 2.8.0, `requirements-build.txt`, `scripts/prepare_models.py`, source tests, smoke checks and `.github/workflows/windows-installer.yml`. End users need only the resulting installer. Tested Kronos source revision and checkpoint hashes are retained in the model manifest. Kronos MIT; TimesFM 2.5 Apache-2.0; notices/model cards accompany assets.

Official sources: [BloFin API](https://docs.blofin.com/), [Kronos](https://github.com/shiyu-coder/Kronos), [TimesFM](https://github.com/google-research/timesfm).
