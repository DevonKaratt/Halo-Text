"""Opt-in Windows test. Briefly displays only an owned synthetic document."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
from halo_text.paths import configure, ROOT
configure()
from halo_text.windows import enable_dpi_awareness, require_windows
require_windows()
enable_dpi_awareness()
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtTest import QTest
from halo_text.capture import ScreenCapture
from halo_text.config import Config
from halo_text.core import Box, TextBlock, Translation
from halo_text.demo import sample_image
from halo_text.overlay import Overlay
from halo_text.windows import hotkey_filter

app=QApplication([])
from halo_text.fonts import load_fonts
load_fonts()
screen=app.primaryScreen()
fixture=QLabel()
fixture.setWindowTitle("HALO TEXT native self-test")
fixture.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool)
fixture.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
image=sample_image()
available=screen.availableGeometry()
width=min(1000,available.width()-60)
height=round(width*620/1000)
fixture.setPixmap(QPixmap.fromImage(image).scaled(width,height))
fixture.setGeometry(available.x()+20,available.y()+20,width,height)
overlay=None
capture=None
hotkeys=None
outline=None
try:
    fixture.show()
    QTest.qWait(500)
    capture=ScreenCapture(screen)
    geometry=fixture.geometry()
    screen_geometry=screen.geometry()
    region=capture.mapping.to_physical((geometry.x()-screen_geometry.x(),
        geometry.y()-screen_geometry.y(),geometry.width(),geometry.height()))
    baseline=capture.grab(region)
    if float(baseline.mean())<100:
        raise RuntimeError("Synthetic fixture was not captured correctly")
    overlay=Overlay(screen,Config())
    if not overlay.excluded:
        raise RuntimeError("Windows overlay capture exclusion failed")
    block=TextBlock("Welcome to our project.",Box(40,40,700,60),1.0,45,background=(255,255,255))
    displayed,skipped=overlay.show_translations(
        [Translation(block,"हमारी परियोजना में आपका स्वागत है।")],capture.mapping,region)
    QTest.qWait(400)
    after=capture.grab(region)
    max_difference=int(np.abs(after.astype(np.int16)-baseline.astype(np.int16)).max())
    changed_fraction=float(np.mean(np.any(after!=baseline,axis=2)))
    if changed_fraction>0.001:
        raise RuntimeError(f"Overlay leaked into capture: {changed_fraction:.4%}")
    from halo_text.outline import SelectionOutline
    outline=SelectionOutline(screen)
    assert outline.excluded
    outline.set_region(capture.mapping,region,True)
    QTest.qWait(200)
    with_border=capture.grab(region)
    if not np.array_equal(with_border,baseline):
        raise RuntimeError("Selection border leaked into screen capture")
    user=ctypes.windll.user32
    get_style=user.GetWindowLongPtrW
    get_style.argtypes=[wintypes.HWND,ctypes.c_int]
    get_style.restype=ctypes.c_ssize_t
    style=get_style(int(overlay.winId()),-20)
    if not style & 0x20 or not style & 0x08000000:
        raise RuntimeError("Overlay is not transparent to input / non-activating")
    user.WindowFromPoint.argtypes=[wintypes.POINT]
    user.WindowFromPoint.restype=wintypes.HWND
    under=user.WindowFromPoint(wintypes.POINT(region.x+region.w//2,region.y+region.h//2))
    if int(under or 0)==int(overlay.winId()):
        raise RuntimeError("Overlay intercepts input")
    received=[]
    hotkeys=hotkey_filter(received.append)
    app.installNativeEventFilter(hotkeys)
    user.PostThreadMessageW(ctypes.windll.kernel32.GetCurrentThreadId(),0x0312,1,0)
    QTest.qWait(150)
    if received != ["translate"]:
        raise RuntimeError("Native hotkey message was not dispatched")
    report={"selection_border_capture_exclusion":True,"native_hotkey_dispatch":True,"capture_exclusion":True,"click_through_style":True,
            "non_activating_style":True,"overlay_hit_test_passes_through":True,
            "displayed_blocks":displayed,"captured_changed_fraction":changed_fraction,
            "max_capture_difference":max_difference,"hotkey_conflicts":hotkeys.failures,
            "screen_scale":[capture.mapping.sx,capture.mapping.sy]}
    (ROOT/"reports"/"native_smoke.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
finally:
    if hotkeys:hotkeys.close()
    if overlay:overlay.close()
    if outline:outline.close()
    fixture.close()
    if capture:capture.close()
    app.processEvents()
