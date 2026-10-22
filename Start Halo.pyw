"""The single user-facing launcher; all application files stay in this folder."""
import ctypes,os,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent
interpreter=root/".venv/Scripts/pythonw.exe"
for folder in ("runtime/temp","runtime/state","runtime/bytecode"):
    (root/folder).mkdir(parents=True,exist_ok=True)
if not interpreter.exists():
    ctypes.windll.user32.MessageBoxW(None,"First open a terminal here and run: python setup/setup_halo.py","HALO TEXT setup required",0x40)
else:
    env=dict(os.environ,TEMP=str(root/"runtime/temp"),TMP=str(root/"runtime/temp"),PYTHONPYCACHEPREFIX=str(root/"runtime/bytecode"))
    with (root/"runtime/state/startup.log").open("a",encoding="utf-8") as log:
        subprocess.Popen([str(interpreter),str(root/"app/launch.pyw")],cwd=root,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
