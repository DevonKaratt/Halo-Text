from types import SimpleNamespace
import numpy as np
import pytest
from halo_text.ocr import ScreenOCR
from halo_text.config import Config

class FakeEngine:
 def __init__(self,fail=False):
  self.cfg=SimpleNamespace(Global=SimpleNamespace(use_vertical_padding=True))
  self.seen=[];self.fail=fail
 def __call__(self,image,**kwargs):
  self.seen.append((image.shape,self.cfg.Global.use_vertical_padding))
  if self.fail:raise RuntimeError('inference failed')
  return SimpleNamespace(boxes=np.array([[[10,10],[110,10],[110,35],[10,35]]]),txts=['Hello world'],scores=[.99])

def make_ocr(fail=False):
 ocr=ScreenOCR.__new__(ScreenOCR);ocr.config=Config();ocr.engine=FakeEngine(fail);return ocr

def test_caption_path_disables_padding_and_maps_scaled_coordinates():
 ocr=make_ocr();lines=ocr.recognize_lines(np.zeros((120,1920,3),dtype=np.uint8),True)
 assert ocr.engine.seen==[((60,960,3),False)]
 assert ocr.engine.cfg.Global.use_vertical_padding is True
 assert lines[0].box.x==20 and lines[0].box.w==200

def test_document_and_tiny_selections_retain_existing_padding():
 ocr=make_ocr()
 for shape,fast in [((600,900,3),True),((30,900,3),True),((100,900,3),False)]:
  ocr.recognize_lines(np.zeros(shape,dtype=np.uint8),fast)
 assert all(padding for _,padding in ocr.engine.seen)

def test_caption_exception_restores_document_padding():
 ocr=make_ocr(True)
 with pytest.raises(RuntimeError):ocr.recognize_lines(np.zeros((100,900,3),dtype=np.uint8),True)
 assert ocr.engine.cfg.Global.use_vertical_padding is True
