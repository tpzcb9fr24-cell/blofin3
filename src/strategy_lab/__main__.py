"""Frozen entry point: smoke failures must never open a blocking error dialog."""
import os
import sys
import traceback
from pathlib import Path

try:
    from strategy_lab.app import main
    main()
except Exception:
    detail=traceback.format_exc()
    try:Path('startup-error.log').write_text(detail,encoding='utf-8')
    except OSError:pass
    if any(flag in sys.argv for flag in ('--self-test','--network-smoke','--model-smoke','--live-smoke','--acceptance-smoke')):
        try:sys.stderr.write(detail)
        except Exception:pass
        os._exit(1)
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(0,'BloFin Observer could not start. Details were saved in startup-error.log.\n\n'+detail[-1500:],'BloFin Observer startup error',0x10)
        os._exit(1)
    raise
