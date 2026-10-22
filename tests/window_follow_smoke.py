"""Native Win32 binding check against a temporary sample window in another process."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
from halo_text.windows import enable_dpi_awareness,window_at,window_rect

enable_dpi_awareness()
if len(sys.argv)>1 and sys.argv[1]=="--child":
    from PySide6.QtWidgets import QApplication,QWidget
    from PySide6.QtCore import Qt
    app=QApplication([])
    window=QWidget()
    window.setWindowTitle("HALO follow-window sample")
    window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    area=app.primaryScreen().availableGeometry()
    window.setGeometry(area.x()+80,area.y()+80,400,200)
    window.show();window.raise_();app.processEvents()
    print(json.dumps({"hwnd":int(window.winId()),"rect":window_rect(int(window.winId()))}),flush=True)
    sys.exit(app.exec())

process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),"--child"],
    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
hwnd=None
try:
    item=json.loads(process.stdout.readline())
    hwnd=item["hwnd"]
    original=window_rect(hwnd)
    assert window_at(*original)==hwnd,(window_at(*original),hwnd)
    user=ctypes.windll.user32
    user.MoveWindow.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.BOOL]
    assert user.MoveWindow(hwnd,original[0]+40,original[1]+25,original[2],original[3],True)
    updated=window_rect(hwnd)
    assert updated[:2]==(original[0]+40,original[1]+25),(original,updated)
    print("Window binding and movement verified")
finally:
    if process.poll() is None:
        if hwnd is not None:
            user=ctypes.windll.user32
            user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
            user.PostMessageW(hwnd,0x10,0,0)
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)
