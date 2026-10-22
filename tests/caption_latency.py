"""Latency test on this process's own synthetic subtitle window, not user content."""
from pathlib import Path
import sys,json,statistics,argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
from time import monotonic
from halo_text.paths import configure,ROOT
configure()
from halo_text.pipeline import preload_runtime
preload_runtime()
from halo_text.windows import enable_dpi_awareness
enable_dpi_awareness()
from PySide6.QtCore import Qt,QTimer,QEventLoop,QObject,Slot
from PySide6.QtGui import QPixmap,QImage,QPainter,QFont,QColor
from PySide6.QtWidgets import QApplication,QLabel
from halo_text.fonts import load_fonts
from halo_text.config import Config
from halo_text.app import Controller
parser=argparse.ArgumentParser()
parser.add_argument("--target",choices=("hi","ta"),default="hi")
args=parser.parse_args()
app=QApplication([]);app.setQuitOnLastWindowClosed(False);load_fonts()
fixture=QLabel();fixture.setWindowTitle('HALO owned caption latency fixture')
fixture.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool)
a=app.primaryScreen().availableGeometry();fixture.setGeometry(a.x()+40,a.y()+100,900,110)
blank=QPixmap(900,110);blank.fill(QColor('black'));fixture.setPixmap(blank);fixture.show()
controller=None
sentences=['The train is arriving at the station.','We need to find another way home.','Please turn off the lights before you leave.','I will call you after the meeting.','The children are playing in the garden.','Let us start with a simple example.','She bought three books yesterday.','Thank you for helping us today.']
rows=[];pending={};errors=[]
def wait_for(predicate,seconds=30):
 end=monotonic()+seconds;loop=QEventLoop();timer=QTimer();timer.setInterval(10)
 timer.timeout.connect(lambda:loop.quit() if predicate() or monotonic()>end else None)
 timer.start();loop.exec();timer.stop()
 if not predicate():raise RuntimeError('Native caption test timed out: '+str(rows)+' '+str(controller.control('status')))
def show_caption(index):
 text=sentences[index];image=QImage(900,110,QImage.Format.Format_RGB32);image.fill(QColor('black'))
 painter=QPainter(image);font=QFont('Segoe UI');font.setPixelSize(28);painter.setFont(font);painter.setPen(QColor('white'));painter.drawText(24,65,text);painter.end()
 pending.clear();pending.update(text=text,started=monotonic(),index=index)
 fixture.setPixmap(QPixmap.fromImage(image));fixture.repaint()
def received(generation,result):
 if not pending or generation!=controller.completed_generation or not controller.overlay.items:return
 source=' '.join(t.block.text for t in result.translations)
 if source!=pending['text']:
  errors.append({'expected':pending['text'],'recognized':source});return
 rows.append({'index':pending['index'],'end_to_end_ms':round((monotonic()-pending['started'])*1000,1),**result.metrics})
 pending.clear()
class Observer(QObject):
 @Slot(int,object)
 def result(self,generation,result):
  received(generation,result)
observer=Observer()
try:
 controller=Controller(app,Config(target=args.target,fast_captions=True,backend="auto"));wait_for(lambda:controller.ready)
 assert not controller.hotkeys.failures,controller.hotkeys.failures
 g=fixture.geometry();origin=app.primaryScreen().geometry()
 controller.region=controller.capture.mapping.to_physical((g.x()-origin.x(),g.y()-origin.y(),g.width(),g.height()))
 controller.invalidate();controller.set_auto(True);controller.show_outline();controller.wanted=True
 controller.worker.result.connect(observer.result,Qt.ConnectionType.QueuedConnection)
 # Fixed cadence, not delayed by completion. Detect any misses or late results.
 show_caption(0)
 for index in range(1,len(sentences)):
  QTimer.singleShot(index*1500,lambda i=index:show_caption(i))
 wait_for(lambda:len(rows)==len(sentences),seconds=30)
 assert len({row['index'] for row in rows})==len(sentences)
 report={'scope':f'Eight generated one-line white captions on solid black; local {args.target}; warm models; 1.5 s fixed cadence. Includes screen change, timer waits, capture, OCR, translation and overlay submission; excludes physical display scanout. Not real-video validation.','captions':rows,'median_ms':round(statistics.median(r['end_to_end_ms'] for r in rows),1),'max_ms':max(r['end_to_end_ms'] for r in rows),'under_one_second':sum(r['end_to_end_ms']<1000 for r in rows),'missed':len(sentences)-len(rows),'earlier_frame_results':errors,'target':args.target}
 (ROOT/'reports'/('caption_latency_tamil.json' if args.target=='ta' else 'caption_latency.json')).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2),flush=True)
finally:
 if controller:
  controller.quit();wait_for(lambda:not controller.thread.isRunning());app.processEvents()
 fixture.close()
