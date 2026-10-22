import ctypes,os,sys,traceback
from pathlib import Path
root=Path(__file__).resolve().parents[1]
os.chdir(root)
sys.pycache_prefix=str(root/"runtime/bytecode")
(root/"runtime/state").mkdir(parents=True,exist_ok=True)
stream=(root/"runtime/state/startup.log").open("a",encoding="utf-8",buffering=1)
sys.stdout=stream
sys.stderr=stream
try:
    from run import main
    main()
except Exception:
    traceback.print_exc()
    ctypes.windll.user32.MessageBoxW(None,"HALO could not start. See runtime/state/startup.log. For repair, run python setup/setup_halo.py.","HALO TEXT",0x10)
