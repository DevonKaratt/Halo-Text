"""Native floating controls test. Uses only this process's synthetic fixture and windows."""
from pathlib import Path
import sys,json,ctypes
from ctypes import wintypes
from time import monotonic
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
from halo_text.paths import configure,ROOT
configure()
from halo_text.pipeline import preload_runtime
preload_runtime()
from halo_text.windows import enable_dpi_awareness
enable_dpi_awareness()
import numpy as np
from PySide6.QtCore import Qt,QEvent,QPoint,QPointF,QTimer,QEventLoop
from PySide6.QtGui import QPixmap,QMouseEvent
from PySide6.QtWidgets import QApplication,QLabel,QMessageBox
from PySide6.QtTest import QTest
from halo_text.app import Controller
from halo_text.config import Config
from halo_text.fonts import load_fonts
from halo_text.demo import sample_image
from halo_text.core import Box

app=QApplication([])
app.setQuitOnLastWindowClosed(False)
load_fonts()
screen=app.primaryScreen()
available=screen.availableGeometry()
fixture=QLabel()
fixture.setWindowTitle("HALO TEXT floating icon verification")
fixture.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool)
fixture.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
width=min(1000,available.width()-60)
height=round(width*620/1000)
fixture.setGeometry(available.x()+20,available.y()+30,width,height)
fixture.setPixmap(QPixmap.fromImage(sample_image()).scaled(width,height))
fixture.show()
controller=None
initial_position=None

def wait_for(condition,seconds=35):
    deadline=monotonic()+seconds
    loop=QEventLoop()
    timer=QTimer()
    timer.setInterval(40)
    timer.timeout.connect(lambda:loop.quit() if condition() or monotonic()>=deadline else None)
    timer.start()
    loop.exec()
    timer.stop()
    if not condition():
        raise RuntimeError("Floating workflow timed out")

def pause(milliseconds):
    loop=QEventLoop()
    QTimer.singleShot(milliseconds,loop.quit)
    loop.exec()

def drag_to(widget,destination):
    point=QPointF(34,34)
    start=QPointF(widget.mapToGlobal(QPoint(34,34)))
    end=QPointF(destination+QPoint(34,34))
    for kind,global_position,button,buttons in (
            (QEvent.Type.MouseButtonPress,start,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton),
            (QEvent.Type.MouseMove,end,Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton),
            (QEvent.Type.MouseButtonRelease,end,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)):
        event=QMouseEvent(kind,point,global_position,button,buttons,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(widget,event)

try:
    controller=Controller(app,Config(target="ta",backend="auto"))
    initial_position=controller.floating.pos()
    wait_for(lambda:controller.ready)
    assert controller.floating.isVisible() and controller.floating.excluded
    assert not controller.hotkeys.failures,controller.hotkeys.failures
    g=fixture.geometry()
    origin=screen.geometry()
    region=controller.capture.mapping.to_physical((
        g.x()-origin.x(),g.y()-origin.y(),g.width(),g.height()))
    # Hide the icon for a baseline, then put it inside the owned sample window.
    controller.set_floating_visible(False)
    pause(150)
    baseline=controller.capture.grab(region)
    controller.set_floating_visible(True)
    destination=QPoint(g.x()+width-100,g.y()+80)
    drag_to(controller.floating,destination)
    assert controller.floating.pos()==destination
    saved=json.loads((ROOT/"runtime/state"/"floating.json").read_text())
    assert saved=={"x":destination.x(),"y":destination.y()}
    pause(200)
    after=controller.capture.grab(region)
    assert np.array_equal(baseline,after),"Floating icon leaked into OCR capture"
    controller.floating.grab().save(str(ROOT/"reports"/"floating_icon.png"))
    # Windows delivers its real context-menu message to the icon's native handle.
    user=ctypes.windll.user32
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    point=controller.floating.mapToGlobal(QPoint(34,34))
    packed=(point.x()&0xffff)|((point.y()&0xffff)<<16)
    user.PostMessageW(int(controller.floating.winId()),0x0204,2,34|(34<<16))
    user.PostMessageW(int(controller.floating.winId()),0x0205,0,34|(34<<16))
    wait_for(lambda:controller.floating_menu.isVisible(),5)
    assert controller.controls_depth>0
    actions=controller.floating_menu.actions()
    assert controller.auto_action in actions and controller.original_action in actions
    assert controller.language_menu.menuAction() in actions
    assert controller.help_action in actions
    controller.floating_menu.grab().save(str(ROOT/"reports"/"floating_controls.png"))
    assert controller.caption_action in actions
    controller.caption_action.trigger()
    assert controller.config.fast_captions and controller.timer.interval()==50
    controller.caption_action.trigger()
    assert not controller.config.fast_captions and controller.timer.interval()==350
    controller.populate_languages()
    indian_menu=next(a.menu() for a in controller.language_menu.actions()
                     if a.menu() and a.text()=="Indian languages")
    telugu=next(a for a in indian_menu.actions() if a.text().startswith("Telugu ("))
    controller.populate_downloaded_models()
    model_labels=[a.text() for a in controller.models_menu.actions()]
    assert controller.models_menu.menuAction() in actions
    assert any("Tamil, Telugu, Bodo, Kashmiri" in label and "in use" in label for label in model_labels)
    assert any("English speech recognition" in label for label in model_labels)
    controller.floating_menu.close()
    wait_for(lambda:controller.controls_depth==0,5)
    assert controller.spoken_action in controller.audio_menu.actions()
    assert controller.config.audio_voice_rate==50
    controller.download_action.trigger()
    wait_for(lambda:controller.model_download is None and controller.ready,25)
    assert controller.config.target=="ta"
    assert controller.control("status")["active_provider"]=="indic"
    telugu.trigger()
    wait_for(lambda:controller.ready and controller.config.target=="te")
    assert "Telugu" in controller.floating_header.text()
    hide=next(a for a in actions if a.text()=="Hide floating icon")
    hide.trigger()
    assert not controller.floating.isVisible() and not controller.floating_action.isChecked()
    controller.floating_action.trigger()
    assert controller.floating.isVisible() and controller.floating.excluded
    # Double-clicking selects the icon's current monitor.
    QTest.mouseDClick(controller.floating,Qt.MouseButton.LeftButton,pos=QPoint(34,34))
    wait_for(lambda:controller.selector is not None,5)
    controller.selector.cancel()
    help_seen=[]
    def close_help():
        for widget in app.topLevelWidgets():
            if isinstance(widget,QMessageBox) and widget.windowTitle()=="HALO TEXT controls":
                assert controller.controls_depth>0
                assert "Ctrl+Alt+R" in widget.informativeText()
                assert "English only" in widget.informativeText()
                help_seen.append(True)
                widget.done(QMessageBox.StandardButton.Ok)
    QTimer.singleShot(250,close_help)
    controller.help_action.trigger()
    assert help_seen and controller.controls_depth==0
    report={"floating_visible":True,"drag_and_saved_position":True,
            "native_right_click_opens_controls":True,"shared_controls":True,
            "output_language_changed_from_menu":"te",
            "hide_and_restore_from_tray":True,"double_click_selects_area":True,
            "shortcut_help":True,"capture_exclusion":True,"caption_toggle":True,"offline_model_control":True,"tamil_offline_download_control":True,"downloaded_models_menu":True,"audio_voice_controls":True,
            "captured_changed_pixels":int(np.count_nonzero(after!=baseline)),
            "hotkey_conflicts":controller.hotkeys.failures}
    (ROOT/"reports"/"floating_smoke.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2),flush=True)
finally:
    if controller:
        if initial_position is not None:
            controller.floating.move(initial_position)
        controller.quit()
        wait_for(lambda:not controller.thread.isRunning())
        app.processEvents()
    fixture.close()
