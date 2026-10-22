from pathlib import Path
import sys,os,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
from halo_text.paths import configure,ROOT
configure();os.environ['QT_QPA_PLATFORM']='offscreen'
from halo_text.pipeline import preload_runtime
preload_runtime()
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QFont,QColor
from halo_text.fonts import load_fonts
from halo_text.config import Config
from halo_text.ocr import ScreenOCR
from halo_text.demo import image_array
app=QApplication([]);load_fonts();ocr=ScreenOCR(Config());rows=[]
for size in [20,28,36]:
 for color,background in [('white','black'),('black','white'),('yellow','#202030')]:
  image=QImage(1200,180,QImage.Format.Format_RGB32);image.fill(QColor(background));p=QPainter(image);f=QFont('Segoe UI');f.setPixelSize(size);p.setFont(f);p.setPen(QColor(color))
  lines=['The next train arrives in 25 minutes.','Please keep your ticket with you.']
  for i,text in enumerate(lines):p.drawText(35,60+i*55,text)
  p.end();output=ocr.recognize(image_array(image),fast_captions=True);recognized=' '.join(b.text for b in output)
  rows.append({'font_px':size,'foreground':color,'background':background,'exact_match':recognized==' '.join(lines),'recognized':recognized})
report={'scope':'Generated two-line captions only; nine font/color combinations, no moving backgrounds.','cases':rows,'exact_matches':sum(r['exact_match'] for r in rows)}
(ROOT/'reports'/'caption_layout_check.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
assert all(r['exact_match'] for r in rows)
