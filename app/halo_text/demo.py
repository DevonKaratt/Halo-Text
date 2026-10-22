"""Generated, non-sensitive test document and repeatable end-to-end benchmark."""
import json
import os
from time import perf_counter
import numpy as np
from .paths import ROOT

SAMPLE_LINES = [
    ("Welcome to our project.", 38, 42, 32),
    ("Technology helps people communicate.", 38, 108, 24),
    ("Please read the instructions carefully.", 38, 154, 24),
    ("The meeting will start tomorrow morning.", 38, 200, 24),
    ("Education is important for everyone.", 38, 290, 27),
    ("Students can learn new skills every day.", 38, 346, 24),
    ("This application translates English into Hindi.", 38, 392, 24),
    ("Save your work before closing the window.", 38, 482, 24),
    ("Click here to continue.", 38, 538, 24),
]

def sample_image():
    from PySide6.QtGui import QImage, QPainter, QColor, QFont
    image = QImage(1000,620,QImage.Format.Format_RGB32)
    image.fill(QColor("#f8fafc"))
    painter = QPainter(image)
    painter.fillRect(20,24,960,210,QColor("#ffffff"))
    painter.fillRect(20,268,960,160,QColor("#eef4ff"))
    painter.fillRect(20,460,960,118,QColor("#ffffff"))
    for text,x,y,size in SAMPLE_LINES:
        painter.setPen(QColor("#172033"))
        font = QFont("Segoe UI")
        font.setPixelSize(size)
        painter.setFont(font)
        painter.drawText(x,y+size,text)
    painter.end()
    return image

def image_array(image):
    converted = image.convertToFormat(image.Format.Format_RGBA8888)
    data = np.frombuffer(converted.constBits(),dtype=np.uint8).reshape(
        converted.height(),converted.bytesPerLine()//4,4)
    return data[:,:converted.width(),:3][:,:,::-1].copy()

def edit_distance(a,b):
    row = list(range(len(b)+1))
    for i,ca in enumerate(a,1):
        current = [i]
        for j,cb in enumerate(b,1):
            current.append(min(current[-1]+1,row[j]+1,row[j-1]+(ca!=cb)))
        row = current
    return row[-1]

def main(benchmark=False,config=None):
    if benchmark:
        os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
    from PySide6.QtWidgets import QApplication, QLabel
    from PySide6.QtGui import QPixmap, QPainter
    app = QApplication.instance() or QApplication([])
    from .fonts import load_fonts
    load_fonts()
    image = sample_image()
    if not benchmark:
        label = QLabel()
        label.setWindowTitle("HALO TEXT sample | Ctrl+Alt+R: select text | Ctrl+Alt+C: clear")
        label.setPixmap(QPixmap.fromImage(image))
        label.resize(image.size())
        label.show()
        return app.exec()
    from .config import load_config
    from .pipeline import Pipeline
    from .overlay import prepare_paint_blocks, paint_blocks
    config = config or load_config()
    from .languages import language
    target_name=language(config.target).name.lower()
    started = perf_counter()
    pipeline = Pipeline(config)
    load_ms = (perf_counter()-started)*1000
    frame = image_array(image)
    cold = pipeline.process(frame)
    warm = pipeline.process(frame)
    items, skipped = prepare_paint_blocks(cold.translations,config)
    preview = image.copy()
    painter = QPainter(preview)
    paint_blocks(painter,items)
    painter.end()
    directory = ROOT / "reports"
    image.save(str(directory/"demo_english.png"))
    preview.save(str(directory/f"demo_{target_name}.png"))
    normalize = lambda text: " ".join(text.lower().split())
    reference = normalize(" ".join(line[0] for line in SAMPLE_LINES))
    recognized = normalize(" ".join(item.block.text for item in cold.translations))
    report = {
        "fixture":"Generated English sample; this is not a real-world quality evaluation",
        "backend":config.backend, "target":config.target, "initialization_ms":round(load_ms,1),
        "cold":cold.metrics,"warm":warm.metrics,
        "displayed_blocks":len(items),"skipped_blocks":skipped,
        "ocr_character_error_rate":round(edit_distance(reference,recognized)/len(reference),4),
        "translations":[{"english":item.block.text,"translated":item.text} for item in cold.translations],
    }
    (directory/"benchmark.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=True,indent=2))
    if not cold.translations or not items:
        raise RuntimeError("Benchmark produced no renderable translations")
    if config.target == "hi" and not all(any("\u0900"<=ch<="\u097f" for ch in item.text) for item in cold.translations):
        raise RuntimeError("One or more sample translations contain no Hindi")
    return 0
