"""Generated Russian caption smoke check; requires optional Cyrillic OCR download."""
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"app"))
os.environ["QT_QPA_PLATFORM"]="offscreen"
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from halo_text.config import Config
from halo_text.ocr_packs import installed
from halo_text.pipeline import Pipeline

if not installed("cyrillic"):
    raise SystemExit("Install the Cyrillic OCR pack first")
image=Image.new("RGB",(1000,130),"black")
draw=ImageDraw.Draw(image)
draw.text((30,36),"Добро пожаловать в наш проект.",
          font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf",38),fill="white")
image.save(ROOT/"reports"/"russian_caption_fixture.png")
pipeline=Pipeline(Config(backend="auto",target="en"))
pipeline.warmup()
assert pipeline.ocr.last_source=="en"
pipeline.source_routes["ru","en"]="local"
result=pipeline.process(np.asarray(image),fast_captions=True)
print(json.dumps({"source":result.source,"recognized":[t.block.text for t in result.translations],
                  "translated":[t.text for t in result.translations],"metrics":result.metrics},ensure_ascii=True,indent=2))
assert result.source=="ru" and result.translations
assert any("welcome" in t.text.lower() for t in result.translations)
next_image=Image.new("RGB",(1000,130),"black")
ImageDraw.Draw(next_image).text((30,36),"Сегодня мы начинаем работу.",
    font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf",38),fill="white")
next_result=pipeline.process(np.asarray(next_image),fast_captions=True)
print(json.dumps({"next_source":next_result.source,
                  "next_recognized":[t.block.text for t in next_result.translations],
                  "next_translated":[t.text for t in next_result.translations],
                  "next_metrics":next_result.metrics},ensure_ascii=True,indent=2))
assert next_result.source=="ru" and next_result.translations
(ROOT/"reports"/"russian_caption_smoke.json").write_text(json.dumps({
    "scope":"Generated captions, installed Cyrillic OCR and direct Russian-to-English pack; first then warmed second uncached caption. Excludes detection polling, screen capture and painting.",
    "first":{"source":result.source,"recognized":[t.block.text for t in result.translations],
             "translated":[t.text for t in result.translations],"metrics":result.metrics},
    "second":{"source":next_result.source,"recognized":[t.block.text for t in next_result.translations],
              "translated":[t.text for t in next_result.translations],"metrics":next_result.metrics}},
    ensure_ascii=False,indent=2),encoding="utf-8")
