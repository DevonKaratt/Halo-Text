from pathlib import Path
import sys,os,json,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
os.environ["QT_QPA_PLATFORM"]="offscreen"
from halo_text.paths import configure,ROOT
configure()
from halo_text.config import Config
from halo_text.indic_translation import IndicTranslator
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont,QImage,QPainter,QColor
from PySide6.QtCore import QPointF
from halo_text.fonts import load_fonts
from halo_text.languages import language
from halo_text.overlay import make_layout
app=QApplication([])
load_fonts()
records=[]
source=["Welcome to our project.","The meeting starts tomorrow morning.","There are 25 students in the classroom."]
for target in ("brx","ks"):
    start=time.monotonic()
    translator=IndicTranslator(Config(target=target))
    outputs=translator.translate_many(source)
    item=language(target)
    for english,text in zip(source,outputs):
        assert text and text.casefold()!=english.casefold()
        if target=="brx":
            assert any("\u0900"<=c<="\u097f" for c in text)
        else:
            assert any("\u0600"<=c<="\u06ff" for c in text)
        font=QFont(item.font)
        font.setPixelSize(24)
        layout,_,_=make_layout(text,700,font,item.rtl)
        missing=sum(index==0 for run in layout.glyphRuns() for index in run.glyphIndexes())
        records.append({"code":target,"english":english,"translated":text,"missing_glyphs":missing})
    print(json.dumps({"target":target,"seconds":round(time.monotonic()-start,2),"translations":outputs},ensure_ascii=True),flush=True)
    del translator
folder=ROOT/"reports"/"language-check"
(folder/"indic.json").write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
image=QImage(900,720,QImage.Format.Format_RGB32)
image.fill(QColor("#111827"))
p=QPainter(image)
for index,record in enumerate(records):
    font=QFont(language(record["code"]).font)
    font.setPixelSize(24)
    layout,_,_=make_layout(record["translated"],840,font,language(record["code"]).rtl)
    p.setPen(QColor("white"))
    layout.draw(p,QPointF(25,25+index*110))
p.end()
image.save(str(folder/"indic.png"))
print(json.dumps({"missing_glyphs":sum(r["missing_glyphs"] for r in records)}),flush=True)
assert not any(r["missing_glyphs"] for r in records)
