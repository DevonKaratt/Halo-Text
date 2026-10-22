from pathlib import Path
import sys,json,os
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
from halo_text.paths import configure,ROOT
configure()
os.environ['QT_QPA_PLATFORM']='offscreen'
from halo_text.pipeline import preload_runtime
preload_runtime()
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QFont,QColor
from halo_text.config import load_config
from halo_text.pipeline import Pipeline
from halo_text.demo import image_array,sample_image
app=QApplication([])
from halo_text.fonts import load_fonts
load_fonts()
p=Pipeline(load_config());p.warmup()
full=p.process(image_array(sample_image())).metrics
sentences=['Welcome to our project.','Technology helps people communicate.','Please read the instructions carefully.','The meeting will start tomorrow morning.','Students can learn new skills every day.']
rows=[]
for text in sentences:
    image=QImage(900,100,QImage.Format.Format_RGB32);image.fill(QColor('black'))
    paint=QPainter(image);font=QFont('Segoe UI');font.setPixelSize(28);paint.setFont(font);paint.setPen(QColor('white'));paint.drawText(24,62,text);paint.end()
    image.save(str(ROOT/"reports"/"caption_fixture.png"))
    result=p.process(image_array(image))
    rows.append(dict(result.metrics,recognized=[t.block.text for t in result.translations],output=[t.text for t in result.translations]))
report={'scope':'Synthetic static captions, local Hindi; warm models. First caption cached, four uncached. Excludes scheduling, screen capture and painting.','full_page':full,'caption_strip':rows}
(ROOT/'reports'/'caption_benchmark.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True,indent=2))
