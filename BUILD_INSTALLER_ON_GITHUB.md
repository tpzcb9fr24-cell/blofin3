# Windows installer verification

The default-branch push workflow bundles genuine checkpoints and CPU runtime, builds the executable, tests the frozen program, compiles Inno Setup, installs silently, and tests the installed executable against live BloFin and real models. Only successful jobs publish prerelease assets. See the workflow and README for exact gates and limitations.

The intended final deliverable is the released `BloFinObserver-Setup.exe`, not an older `BloFinStrategyLab` installer. End users do not install Python or upload CSVs. Windows Server automated checks do not replace clean Windows 11 interactive acceptance.
