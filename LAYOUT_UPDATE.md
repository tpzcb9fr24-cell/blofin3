# Display layout update 0.2.3

The 0.2.2 window reserved enough space for the chart and manual entry controls that the trade journal rows could be pushed below the screen on a smaller display. The window's minimum size also exceeded some available desktop work areas. Scrolling a table could not recover a table whose visible height had been squeezed away.

The updated application provides:

- A vertical scrollbar at the far right for the whole page and a horizontal scrollbar along the bottom. Mouse wheel over labels/background also scrolls the page; tables retain their own scrolling.
- A Hide chart / more journal space button, with Show chart to restore it.
- A virtual page large enough to preserve the journal rows and bottom comparison/status text.
- Horizontal and vertical scrollbars on every table, with preserved column widths.
- A starting window constrained to the display size and a smaller minimum window size.

The GUI self-test checks journal row height and access to the bottom status at 1024x640, chart hiding/restoration, tab visibility, horizontal access, and a further resize to 640x480. It also retains the actual manual entry, partial exit, close and database reopening checks. No network or real order is involved in this GUI self-test. The full release workflow separately verifies public data and genuine model inference.

Trading and journal calculations are unchanged. The updater retains installed model assets and the local journal. Close the companion before running the updater, then reopen it and use the far-right page scrollbar to reach the lower journal section.

A user-provided Windows 11 photo confirmed that build 7 displayed live prices, candles and forecasts on the affected machine. This update's specific layout still needs interactive confirmation on that machine. Annotated SMC/TP validation remains outstanding.

## Published verification

[Build 8 release](https://github.com/alyssa24aj-lgtm/blofin2/releases/tag/observer-8), source `7e6a1a3c8571c67de14e358917bbbe0034ddd0e9`.

[Windows workflow](https://github.com/alyssa24aj-lgtm/blofin2/actions/runs/39775269341) passed 36 unit tests, source/frozen/installed GUI checks, public REST and actual WebSocket pushes, genuine models, a fresh installation, and the updater over the released 0.2.1 installation with retained model hashes. The Windows layout test measured 302 pixels of journal height at 1024x640 and confirmed bottom access and chart toggle. Evidence is in `verification/windows-build-8/`.

- Updater: 143,000,363 bytes; SHA-256 `81645ab2372db1a81b9f6c787beb9a23dbe309fff5b7afabd0d42dbab9a08c33`.
- Full setup: 1,106,603,106 bytes; SHA-256 `857bb5037c3515b8515f7085b41b2c57a40742f051cbb22f02e0eb2e16167baa`.
