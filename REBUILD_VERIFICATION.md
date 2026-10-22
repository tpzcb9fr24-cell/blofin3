# Windows rebuild verification

Repository: tpzcb9fr24-cell/blofin3. Source: `a88de54d20e42f017b476d00d95ea6b8fac266e3`. Version: 0.2.3.

[Windows workflow](https://github.com/tpzcb9fr24-cell/blofin3/actions/runs/39780896692) / [published assets](https://github.com/tpzcb9fr24-cell/blofin3/releases/tag/observer-1).

Passed 36 unit tests and source/frozen/installed GUI checks; live official public REST and actual WebSocket pushes for BTC/ETH/SOL; genuine Kronos and TimesFM inference; fresh installation; updater applied over the freshly built setup; identical installed TimesFM weight and local journal hashes after updating. GUI layout evidence confirms 302 pixels of journal height at 1024x640, reachable bottom status, and chart hide/show. Evidence files are in `verification/rebuild-1/`.

The previous repository's released baseline is inaccessible. This rebuild does not repeat the updater-over-0.2.1 test; historical evidence for that earlier run remains in the repository. The test platform is Windows Server 2022. Interactive Windows 11 display acceptance, annotated SMC/TP validation, and the other limitations documented in `verification/ACCEPTANCE.md` remain outstanding.

Updater: 143,000,540 bytes; SHA256 `0250c7872e09dd9688d55c3bb5c9e3454681a6f623d7db38a1e9d80aa6d07f81`.

Full setup: 1,106,603,255 bytes; SHA256 `fcc6974c894343d66a3c7433c990e3bfc7abd7af66a2bcb0797a952d91edc55a`.
