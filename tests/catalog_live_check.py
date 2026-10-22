"""Opt-in live translation check. Sends only the fixed generated sentence below."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
import json,os
os.environ["QT_QPA_PLATFORM"]="offscreen"
from halo_text.paths import configure,ROOT
configure()
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont,QImage,QPainter,QColor
from PySide6.QtCore import QPointF,QRectF,Qt
from halo_text.fonts import load_fonts
from halo_text.languages import LANGUAGES
from halo_text.config import Config
from halo_text.online import WebTranslator
from halo_text.overlay import make_layout
app=QApplication([])
load_fonts()
sentence="Welcome to our project."
records=[]
folder=ROOT/"reports"/"language-check"
folder.mkdir(exist_ok=True)
for code,item in LANGUAGES.items():
    if code in {"brx","ks"}:
        continue
    try:
        translated=WebTranslator(Config(backend="web",target=code)).translate_many([sentence])[0]
        if translated.casefold()==sentence.casefold():
            raise RuntimeError("Service returned unchanged English")
        font=QFont(item.font)
        font.setPixelSize(22)
        layout,_,_=make_layout(translated,400,font,item.rtl)
        missing=sum(index==0 for run in layout.glyphRuns() for index in run.glyphIndexes())
        record={"code":code,"name":item.name,"translated":translated,"missing_glyphs":missing,
                "ok":missing==0}
    except Exception as exc:
        record={"code":code,"name":item.name,"ok":False,"error":str(exc)}
    records.append(record)
    print(json.dumps(record,ensure_ascii=True),flush=True)
    (folder/"online.json").write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
for page in range((len(records)+9)//10):
    image=QImage(900,650,QImage.Format.Format_RGB32)
    image.fill(QColor("#111827"))
    p=QPainter(image)
    for index,record in enumerate(records[page*10:page*10+10]):
        x=20+(index%2)*445
        y=15+(index//2)*128
        font=QFont("Segoe UI")
        font.setPixelSize(15)
        p.setFont(font)
        p.setPen(QColor("#86efac" if record["ok"] else "#fca5a5"))
        p.drawText(x,y+20,record["name"]+" ["+record["code"]+"]")
        font=QFont(LANGUAGES[record["code"]].font)
        font.setPixelSize(22)
        layout,_,_=make_layout(record.get("translated",record.get("error","")),400,font,
                               LANGUAGES[record["code"]].rtl)
        p.setPen(QColor("white"))
        layout.draw(p,QPointF(x,y+35))
    p.end()
    image.save(str(folder/f"page-{page+1}.png"))
print(json.dumps({"checked":len(records),"passed":sum(r["ok"] for r in records)}))
raise SystemExit(0 if all(r["ok"] for r in records) else 1)
