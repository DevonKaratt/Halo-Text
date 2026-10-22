"""Optional Spanish caption integration check; requires Latin OCR pack."""
import json,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"app"))
from halo_text.config import Config
from halo_text.ocr_packs import installed
from halo_text.pipeline import Pipeline
if not installed("latin"):
    raise SystemExit("Install Latin OCR pack first")
image=Image.new("RGB",(1000,130),"black")
ImageDraw.Draw(image).text((30,36),"Bienvenidos a nuestro proyecto.",
    font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf",38),fill="white")
pipeline=Pipeline(Config(backend="auto",target="en"))
pipeline.source_routes["es","en"]="web"
result=pipeline.process(np.asarray(image),fast_captions=True)
print(json.dumps({"source":result.source,"recognized":[x.block.text for x in result.translations],
                  "translated":[x.text for x in result.translations],"metrics":result.metrics},ensure_ascii=True,indent=2))
assert result.source=="es" and result.translations
assert "welcome" in result.translations[0].text.lower()
