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
parser.add_argument('--target',default='hi')
parser.add_argument('--baseline',action='store_true')
args=parser.parse_args()
app=QApplication([]);app.setQuitOnLastWindowClosed(False);load_fonts()
fixture=QLabel();fixture.setWindowTitle('HALO owned moving-caption fixture')
fixture.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool)
a=app.primaryScreen().availableGeometry();fixture.setGeometry(a.x()+40,a.y()+100,900,110)
blank=QPixmap(900,110);blank.fill(QColor('black'));fixture.setPixmap(blank);fixture.show()
class BaselineConfig(Config):
 def watch_timing(self):
  return (150,200,500)
controller=None
sentences=['The train is arriving at the station.','We need to find another way home.','Please turn off the lights before you leave.','I will call you after the meeting.','The children are playing in the garden.','Let us start with a simple example.','She bought three books yesterday.','Thank you for helping us today.']
rows=[];pending={};errors=[]
def wait_for(predicate,seconds=30):
 end=monotonic()+seconds;loop=QEventLoop();timer=QTimer();timer.setInterval(10)
 timer.timeout.connect(lambda:loop.quit() if predicate() or monotonic()>end else None)
 timer.start();loop.exec();timer.stop()
 if not predicate():raise RuntimeError('Native caption test timed out: '+str(rows)+' '+str(controller.control('status')))
current_text=''
movie_frame=0
late_results=0
def draw_movie():
 global movie_frame
 movie_frame+=1
 image=QImage(900,110,QImage.Format.Format_RGB32)
 image.fill(QColor(15+movie_frame*3%60,20+movie_frame*5%60,25+movie_frame*7%60))
 painter=QPainter(image)
 painter.fillRect((movie_frame*23)%1000-100,0,120,110,QColor(65,50,80))
 font=QFont('Segoe UI');font.setPixelSize(28);painter.setFont(font)
 painter.setPen(QColor('black'));painter.drawText(26,67,current_text)
 painter.setPen(QColor('white'));painter.drawText(24,65,current_text);painter.end()
 fixture.setPixmap(QPixmap.fromImage(image));fixture.repaint()
def show_caption(index):
 global current_text
 current_text=sentences[index]
 pending.clear();pending.update(text=current_text,started=monotonic(),index=index)
 draw_movie()

def received(generation,result):
 if not pending or generation!=controller.completed_generation or not controller.overlay.items:return
 source=' '.join(t.block.text for t in result.translations)
 if source!=pending['text']:
  return  # A bounded delayed sample may finish just after the next caption begins.
 assert controller.overlay.isVisible(), 'Translated overlay window is hidden'
 if not rows:
  from PySide6.QtCore import QRect
  m=controller.capture.mapping;r=controller.region
  controller.overlay.grab(QRect(round(r.x/m.sx),round(r.y/m.sy),round(r.w/m.sx),round(r.h/m.sy))).save(str(ROOT/'reports'/('caption_visible_'+args.target+'.png')))
 rows.append({'index':pending['index'],'end_to_end_ms':round((monotonic()-pending['started'])*1000,1),**result.metrics})
 pending.clear()
class Observer(QObject):
 @Slot(int,object)
 def result(self,generation,result):
  received(generation,result)
observer=Observer()
try:
 controller=Controller(app,(BaselineConfig if args.baseline else Config)(fast_captions=True,caption_hold=False,target=args.target,backend='auto'));wait_for(lambda:controller.ready)
 assert not controller.hotkeys.failures,controller.hotkeys.failures
 g=fixture.geometry();origin=app.primaryScreen().geometry()
 controller.region=controller.capture.mapping.to_physical((g.x()-origin.x(),g.y()-origin.y(),g.width(),g.height()))
 controller.invalidate();controller.set_auto(True);controller.show_outline();controller.wanted=True
 controller.worker.result.connect(observer.result,Qt.ConnectionType.QueuedConnection)
 # Fixed cadence, not delayed by completion. Detect any misses or late results.
 movie=QTimer();movie.setInterval(40);movie.timeout.connect(draw_movie);movie.start()
 show_caption(0)
 for index in range(1,len(sentences)):
  QTimer.singleShot(index*1000,lambda i=index:show_caption(i))
 wait_for(lambda:len(rows)==len(sentences) or bool(errors),seconds=25)
 assert not errors,errors
 assert len({row['index'] for row in rows})==len(sentences)
 current_text='';draw_movie()
 wait_for(lambda:not controller.overlay.items,seconds=5)
 movie.stop()
 report={'scope':'Eight generated one-line captions on a moving/recolored background updated every 40 ms; 1 s fixed cadence. Includes waits, capture, OCR, translation and overlay submission; physical scanout excluded. Synthetic motion, not a movie accuracy evaluation.','target':args.target,'captions':rows,'timing_ms':controller.config.watch_timing(),'median_ms':round(statistics.median(r['end_to_end_ms'] for r in rows),1),'max_ms':max(r['end_to_end_ms'] for r in rows),'under_one_second':sum(r['end_to_end_ms']<1000 for r in rows),'missed':len(sentences)-len(rows),'matched_expected_captions':len(rows),'blank_clears_with_background_still_moving':True}
 (ROOT/'reports'/('caption_native_'+args.target+('_baseline' if args.baseline else '')+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2),flush=True)
finally:
 if controller:
  controller.quit();wait_for(lambda:not controller.thread.isRunning());app.processEvents()
 fixture.close()
