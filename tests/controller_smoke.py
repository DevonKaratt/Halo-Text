"""Full native workflow on an owned sample window; no user content is captured."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
import json
from time import monotonic
from halo_text.paths import ROOT,configure
configure()
import logging
logging.basicConfig(level=logging.INFO)
from halo_text.pipeline import preload_runtime
preload_runtime()
from halo_text.windows import enable_dpi_awareness
enable_dpi_awareness()
from PySide6.QtCore import Qt,QEventLoop,QTimer
from PySide6.QtGui import QPixmap,QColor
from PySide6.QtWidgets import QApplication,QLabel
from PySide6.QtTest import QTest
from halo_text.fonts import load_fonts
from halo_text.demo import sample_image
from halo_text.app import Controller
from halo_text.config import Config

app=QApplication([])
app.setQuitOnLastWindowClosed(False)
load_fonts()
screen=app.primaryScreen()
image=sample_image()
available=screen.availableGeometry()
width=min(1000,available.width()-60)
height=round(width*620/1000)
fixture=QLabel()
fixture.setWindowTitle("HALO TEXT end-to-end self-test")
fixture.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool)
fixture.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
fixture.setGeometry(available.x()+20,available.y()+20,width,height)
pixmap=QPixmap.fromImage(image).scaled(width,height)
fixture.setPixmap(pixmap)
fixture.show()
controller=None

def wait_until(condition,seconds=25):
    deadline=monotonic()+seconds
    loop=QEventLoop()
    timer=QTimer()
    timer.setInterval(50)
    def poll():
        if condition() or monotonic()>=deadline:
            loop.quit()
    timer.timeout.connect(poll)
    timer.start()
    loop.exec()
    timer.stop()
    if not condition():
        from halo_text.windows import desktop_available
        print("Timeout state:",controller.control("status") if controller else None,flush=True)
        if controller:
            print("Capture state:",{"region":str(controller.region),"generation":controller.generation,
                  "wanted":controller.wanted,"display_pending":controller.display_pending,
                  "desktop_available":desktop_available()},flush=True)
        raise RuntimeError("Workflow timed out")

def pause(milliseconds):
    loop=QEventLoop()
    QTimer.singleShot(milliseconds,loop.quit)
    loop.exec()

try:
    controller=Controller(app,Config())
    wait_until(lambda:controller.ready)
    geometry=fixture.geometry()
    origin=screen.geometry()
    controller.region=controller.capture.mapping.to_physical((
        geometry.x()-origin.x(),geometry.y()-origin.y(),geometry.width(),geometry.height()))
    controller.invalidate()
    controller.dispatch("translate")
    wait_until(lambda:bool(controller.overlay.items))
    first_count=len(controller.overlay.items)
    print("Manual overlay:",first_count,"blocks",flush=True)
    controller.dispatch("original")
    assert controller.overlay.original_visible and not controller.overlay.isVisible()
    assert len(controller.overlay.items)==first_count
    controller.dispatch("original")
    assert not controller.overlay.original_visible and controller.overlay.isVisible()
    print("Original/translated comparison passed",flush=True)
    blank=QPixmap(width,height)
    blank.fill(QColor("white"))
    controller.dispatch("original")
    fixture.setPixmap(blank)
    pause(100)
    controller.dispatch("original")
    assert not controller.overlay.items and not controller.overlay.isVisible()
    wait_until(lambda:not controller.overlay.items,seconds=5)
    print("Changed content cleared the overlay",flush=True)
    controller.dispatch("auto")
    pause(1200)
    fixture.setPixmap(pixmap)
    wait_until(lambda:bool(controller.overlay.items))
    print("Automatic translation refreshed",flush=True)
    controller.dispatch("clear")
    pause(600)
    assert not controller.overlay.items and not controller.auto
    controller.dispatch("region")
    assert controller.selector is not None
    old_capture=controller.capture
    controller.display_changed()
    assert controller.selector is None and controller.region is None
    wait_until(lambda:not controller.display_pending,seconds=5)
    assert controller.capture is not old_capture
    controller.region=controller.capture.mapping.to_physical((
        geometry.x()-origin.x(),geometry.y()-origin.y(),geometry.width(),geometry.height()))
    controller.invalidate()
    controller.dispatch("translate")
    wait_until(lambda:bool(controller.overlay.items))
    print("Display recovery and subsequent translation passed",flush=True)
    controller.clear()
    languages={}
    for target in ("es","fr","hi"):
        controller.change_language(target)
        wait_until(lambda:controller.ready and controller.config.target==target)
        controller.dispatch("translate")
        wait_until(lambda:bool(controller.overlay.items))
        languages[target]=len(controller.overlay.items)
        controller.clear()
    print("Live language switching passed:",languages,flush=True)
    controller.populate_monitors()
    assert len(controller.monitor_menu.actions())==len(app.screens())
    report={"original_comparison_toggle":True,"language_switch_blocks":languages,
            "monitor_menu_count":len(controller.monitor_menu.actions()),
            "models_ready":True,"manual_translation_blocks":first_count,
            "display_change_cancels_selection":True,"display_capture_rebuilt":True,
            "translation_after_display_recovery":True,
            "screen_change_clears_overlay":True,"automatic_refresh":True,
            "clear_pauses_updates":True}
    print(json.dumps(report,indent=2),flush=True)
    (ROOT/"reports"/"controller_smoke.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
finally:
    if controller:
        controller.quit()
        wait_until(lambda:not controller.thread.isRunning(),seconds=45)
        app.processEvents()
    fixture.close()
