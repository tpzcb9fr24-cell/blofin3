# Acceptance ledger — 2026-10-21

Status: VERIFIED WINDOWS PRERELEASE. Not claimed as completed clean-Windows-11 or annotated-strategy acceptance.

## Released installer

- [BloFinObserver-Setup.exe](https://github.com/alyssa24aj-lgtm/blofin2/releases/download/observer-6/BloFinObserver-Setup.exe), version 0.2.1, 1,106,544,112 bytes.
- SHA-256: `a022ab28125eedc87b81c8dea3fa89e0894f230b9217068b7277aae6d0b1541a`.
- Source commit: `6a3dd26a99e0328cb9e85bd1deec3e620a6c4b3d`.
- [Successful Windows workflow](https://github.com/alyssa24aj-lgtm/blofin2/actions/runs/39618738658), all steps passed.
- Genuine CPU runtime and model weights are bundled. End users do not install Python or upload CSVs. Observer only, no account credentials or exchange write functionality.

## Verified on Windows

Windows Server 2022, OS build 20348 (not Windows 11): 29 tests passed, real public market data, actual Kronos and TimesFM checkpoint inference, PyInstaller build, frozen GUI/model tests, Inno Setup compilation, silent installation, and installed executable tests.

The installed desktop test loaded BTC-USDT, ETH-USDT, SOL-USDT, produced genuine six-step forecasts from both models for each symbol, saw advancing live updates, recorded a local manual-fill journal entry, and verified the journal after reopening its database. End-to-end desktop startup/checks took about 17.3 seconds. Actual output is retained in `windows-build-6/desktop-smoke.json`; market/model outputs and checkpoint manifest accompany it. These are tests in a temporary journal, not real executed exchange trades.

## Verified locally

- 29 tests pass, including long/short target boundaries, partial/equal touches and far-edge wick invalidation, future/invalid OB exclusion, gap/candle validation, pivot confirmation, model freshness, costs, ambiguous/gapped exits, partial manual exits, audited edits, restart persistence, forecast scoring and public-only exchange transport.
- Actual public BloFin 512-bar histories for BTC-USDT, ETH-USDT, SOL-USDT; 79 websocket updates per symbol during recorded probe; a newly completed five-minute candle seen on all three; reconnect and contiguous REST backfill. See live-stream-evidence.json.
- Genuine Kronos-small + tokenizer, and TimesFM 2.5 200M checkpoint inference, not substitutes. See model-smoke.json and model-manifest.json.
- Linux actual desktop/worker integration: all three live instruments and both real models; quotes continued advancing; manual capture worked; journal survived reopening. See desktop-smoke.json. After analytics/overlays were added, a further real GUI probe loaded all three instruments, six model pairs and ten strategy tracks in ~28 seconds.
- Tk window startup and partial-exit journal control smoke tested with a virtual display. Not a Windows test.

## Still unverified or incomplete

- Clean Windows 11 interactive installation/use. The installer and frozen/installed runtime have passed on Windows Server 2022; this does not establish a clean Windows 11 test.
- Exact annotated SMC examples and intended opposing-block near/far wick boundary remain unavailable/unvalidated. Implemented cap is conservatively before the near edge, before the entire opposing zone. Current provisional settings are exposed, not represented as approved.
- Known order blocks now persist across rolling context and restart; the regression test proves partial touches and first invalidation survive. Full outage reconstruction beyond available backfill and zones never observed by the application remain limitations.
- Simulator is hypothetical: spread is crossed at displayed bid/ask, residual fees/slippage estimated, funding/leverage excluded, unobserved intrabar order unknown. No strategy/model predictive quality is asserted.
- End-user instrument intent (perpetual versus spot) still requires validation; this build explicitly observes BloFin USDT perpetuals and labels that in the UI.

The published binary is a tested prerelease. Exact SMC entry behavior remains an explicit configurable interpretation, not a claim of annotated-example equivalence. Windows 11 acceptance remains open. Public spread is observed, residual costs estimated, funding/leverage excluded. No predictive profitability is asserted.
