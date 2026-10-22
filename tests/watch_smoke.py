"""Native persistent-region workflow on an owned generated page, including blank content."""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
from time import monotonic
from halo_text.paths import configure,ROOT
configure()
from halo_text.pipeline import preload_runtime
preload_runtime()
from halo_text.windows import enable_dpi_awareness
enable_dpi_awareness()
from PySide6.QtCore import Qt,QTimer,QEventLoop,QPoint
from PySide6.QtGui import QPixmap,QImage,QPainter,QColor,QFont
from PySide6.QtWidgets import QApplication,QLabel
from PySide6.QtTest import QTest
from halo_text.fonts import load_fonts
from halo_text.app import Controller
from halo_text.config import Config
from halo_text.demo import sample_image

app=QApplication([])
app.setQuitOnLastWindowClosed(False)
load_fonts()
screen=app.primaryScreen()
available=screen.availableGeometry()
fixture=QLabel()
fixture.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool)
fixture.setWindowTitle("HALO TEXT scroll-watch verification")
width=min(1000,available.width()-60)
height=round(width*620/1000)
fixture.setGeometry(available.x()+20,available.y()+30,width,height)
fixture.setPixmap(QPixmap.fromImage(sample_image()).scaled(width,height))
fixture.show()
controller=None

def wait_for(condition,seconds=35):
    end=monotonic()+seconds
    loop=QEventLoop()
    timer=QTimer()
    timer.setInterval(40)
    timer.timeout.connect(lambda:loop.quit() if condition() or monotonic()>=end else None)
    timer.start()
    loop.exec()
    timer.stop()
    if not condition():
        raise RuntimeError("Watch workflow timed out: "+str(controller.control("status")))

def pause(milliseconds):
    loop=QEventLoop()
    QTimer.singleShot(milliseconds,loop.quit)
    loop.exec()

try:
    controller=Controller(app,Config(fast_captions="--fast" in sys.argv,caption_hold=False,backend="auto",target=sys.argv[1] if len(sys.argv)>1 else "hi"))
    wait_for(lambda:controller.ready)
    controller.choose_region(screen)
    selector=controller.selector
    origin=screen.geometry()
    g=fixture.geometry()
    start=QPoint(g.x()-origin.x(),g.y()-origin.y())
    stop=start+QPoint(width-1,height-1)
    QTest.mousePress(selector,Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(selector,stop)
    QTest.mouseRelease(selector,Qt.MouseButton.LeftButton,pos=stop)
    assert controller.auto and controller.outline.isVisible()
    wait_for(lambda:bool(controller.overlay.items))
    first=len(controller.overlay.items)
    assert controller.outline.isVisible()
    controller.dispatch("original")
    assert controller.outline.isVisible() and not controller.overlay.isVisible()
    controller.dispatch("original")
    blank=QPixmap(width,height)
    blank.fill(QColor("white"))
    fixture.setPixmap(blank)
    wait_for(lambda:not controller.overlay.items)
    pause(2000)
    assert controller.auto and controller.outline.isVisible()
    page=QImage(width,height,QImage.Format.Format_RGB32)
    page.fill(QColor("white"))
    p=QPainter(page)
    f=QFont("Segoe UI")
    f.setPixelSize(28)
    p.setFont(f)
    p.setPen(QColor("black"))
    p.drawText(35,100,"The second page has different English text.")
    p.drawText(35,165,"Please check your internet connection.")
    p.end()
    fixture.setPixmap(QPixmap.fromImage(page))
    wait_for(lambda:bool(controller.overlay.items))
    assert controller.outline.isVisible() and controller.auto
    controller.dispatch("auto")
    assert not controller.auto and controller.outline.isVisible()
    fixture.setPixmap(blank)
    pause(1500)
    assert not controller.overlay.items
    controller.dispatch("auto")
    fixture.setPixmap(QPixmap.fromImage(page))
    wait_for(lambda:bool(controller.overlay.items))
    controller.dispatch("clear")
    assert not controller.auto and not controller.outline.isVisible()
    report={"fast_captions":controller.config.fast_captions,"target":controller.config.target,"drag_release_enables_watching":True,"first_page_blocks":first,
            "border_persists_after_translation":True,"border_persists_on_blank_page":True,
            "new_page_translates_without_reselection":True,"pause_keeps_border":True,
            "resume_works":True,"clear_removes_border":True}
    (ROOT/"reports"/("watch_smoke_fast.json" if controller.config.fast_captions else "watch_smoke.json" if controller.config.target=="hi" else "watch_smoke_"+controller.config.target+".json")).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2),flush=True)
finally:
    if controller:
        controller.quit()
        wait_for(lambda:not controller.thread.isRunning())
        app.processEvents()
    fixture.close()
