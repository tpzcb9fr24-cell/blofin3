# Windows connection update 0.2.2

The installed 0.2.1 client received HTTP 403 for both Python HTTPS and WebSocket requests, while the same public candle endpoint returned JSON in the user's browser. This confirms a request-path difference; it does not prove a particular Cloudflare rule, geographic restriction or proxy configuration caused it.

Windows now uses native WinHTTP/Schannel for public HTTPS and WebSocket connections, using system and per-user proxy settings. It retains certificate verification, identifies itself as BloFinObserver, accepts only official public candle/ticker endpoints, never reads browser cookies, and cannot submit exchange orders. Linux development retains standard public HTTPS/WebSocket transport.

Failures show a concise server denial message instead of pages of HTML. HTTP 403 retries back off to 60 seconds. A working REST connection can continue live updates every three seconds while the socket reconnects. No other exchange data is substituted.

The smaller updater replaces the program/runtime and retains the previously installed model weights and journal. It requires an existing installation; use the full setup for first installation. The build verifies native public REST and genuine WebSocket pushes, then tests both a new installation and the updater applied over the released 0.2.1 installer, including genuine model inference and desktop/journal checks.

Subsequent user-provided Windows 11 photos show live BTC/ETH/SOL prices, candles and model forecasts on the affected PC after the update. The existing Windows 11/annotated-SMC acceptance limitations remain documented in verification/ACCEPTANCE.md.

## Release and verification

Published [build 7](https://github.com/alyssa24aj-lgtm/blofin2/releases/tag/observer-7), source `52b2947643cd41c6fd31b90b9d608df5058486f6`.

- Updater: 142,955,882 bytes; SHA-256 `7b33ab0b2e14219e7e015f67e12a993b94b13232224483b2b9ac63b30f0e5c12`.
- Full installer: 1,106,558,414 bytes; SHA-256 `705a31978585a31ca7a923a8a928eb14c0c3f9c775d0601c1947d6bd9bd0514b`.
- [Successful Windows workflow](https://github.com/alyssa24aj-lgtm/blofin2/actions/runs/39637099489): 36 tests, native public REST and six actual WebSocket updates, genuine inference, frozen runtime, fresh installation, then updater applied over 0.2.1 with preserved TimesFM weight hash and repeated network/model/desktop/journal tests.
- Actual upgraded-app evidence is in `verification/windows-build-7/`. Native REST+WebSocket probe took about 3.36 seconds on the Windows runner.
- Subsequent user-provided Windows 11 photos show working live prices, candles and forecasts on the affected machine. The underlying cause of the prior denial was not established; no claim of resolving a geographic restriction or Cloudflare policy is made.
