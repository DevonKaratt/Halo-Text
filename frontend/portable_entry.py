"""No-console entry point for the portable Windows application."""
import ctypes
import sys
import traceback
from pathlib import Path
from halo_text.paths import ROOT,configure


def main():
    configure()
    installer=any(argument.startswith("--install-") for argument in sys.argv[1:])
    logfile=ROOT/"runtime/state"/("model-download.log" if installer else "startup.log")
    with logfile.open("a",encoding="utf-8",buffering=1) as stream:
        sys.stdout=stream
        sys.stderr=stream
        try:
            if len(sys.argv)==1:
                from halo_text.release_integrity import verify_release
                verify_release()
            from run import main as run_main
            return run_main()
        except Exception as exc:
            traceback.print_exc()
            if len(sys.argv)==1:
                ctypes.windll.user32.MessageBoxW(None,
                    "HALO could not start. Check runtime/state/startup.log.\n"+str(exc)[:280],
                    "HALO TEXT",0x10)
            return 1


if __name__=="__main__":
    raise SystemExit(main())
