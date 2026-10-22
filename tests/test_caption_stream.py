from types import SimpleNamespace
from time import monotonic
import numpy as np
from halo_text.config import Config
from halo_text.app import Controller
from halo_text.core import Box,TextBlock,Translation

def state(monkeypatch):
 monkeypatch.setattr('halo_text.app.desktop_available',lambda:True)
 calls=[]
 s=SimpleNamespace(exiting=False,controls_depth=0,ready=True,selector=None,region=Box(0,0,900,110),auto=True,wanted=False,busy=False,display_pending=False,
  config=Config(fast_captions=True,caption_hold=False),caption_expires_at=0,last_submit=monotonic()-1,generation=4,
  signature=np.zeros((110,900),dtype=np.uint8),overlay=SimpleNamespace(items=[]),
  capture=SimpleNamespace(grab=lambda region:np.full((110,900,3),180,dtype=np.uint8)),
  status=lambda *args,**kwargs:None,request_job=SimpleNamespace(emit=lambda *args:calls.append(args)),
  clear_visuals=lambda:None,update_followed_region=lambda:None)
 return s,calls

def test_moving_pixels_do_not_prevent_caption_submission(monkeypatch):
 s,calls=state(monkeypatch)
 Controller.tick(s)
 assert s.busy and len(calls)==1 and calls[0][0]==4 and calls[0][2] is True
 assert s.generation==4
 Controller.tick(s)
 assert len(calls)==1 and s.generation==4  # No queued backlog while busy.

def test_unchanged_caption_strip_skips_duplicate_ocr(monkeypatch):
 s,calls=state(monkeypatch)
 s.caption_frame=np.full((110,900,3),180,dtype=np.uint8)
 s.overlay.items=[object()]
 s.caption_expires_at=monotonic()+.1
 Controller.tick(s)
 assert not calls and not s.busy
 assert s.caption_expires_at>monotonic()+1
 s.capture.grab=lambda region:np.full((110,900,3),181,dtype=np.uint8)
 Controller.tick(s)
 assert len(calls)==1

def test_too_old_caption_is_discarded(monkeypatch):
 s,calls=state(monkeypatch);s.busy=True;s.last_submit=monotonic()-3
 cleared=[];s.clear_visuals=lambda:cleared.append(True)
 Controller.finished(s,4,SimpleNamespace(translations=[]))
 assert not s.busy and s.job_frame is None and cleared

def test_slow_result_is_displayed_when_source_frame_is_unchanged(monkeypatch):
 s,calls=state(monkeypatch);s.busy=True;s.last_submit=monotonic()-3
 s.job_frame=np.full((110,900,3),180,dtype=np.uint8)
 s.capture.mapping=object()
 painted=[];s.overlay.show_translations=lambda *args:(painted.append(True) or (1,0))
 t=Translation(TextBlock('Hello',Box(10,20,200,30),.99,30),'நமஸ்தே')
 Controller.finished(s,4,SimpleNamespace(translations=[t],metrics={'total_ms':3000}))
 assert painted and s.completed_generation==4

def test_caption_result_can_paint_despite_background_changes(monkeypatch):
 s,calls=state(monkeypatch);s.busy=True;s.last_submit=monotonic()-.3
 s.capture=SimpleNamespace(mapping=object(),grab=lambda region:(_ for _ in ()).throw(AssertionError('Pixel-stability gate must not run')))
 painted=[];s.overlay=SimpleNamespace(items=[],show_translations=lambda *args:(painted.append(True) or (1,0)))
 s.job_frame=np.zeros((110,900,3),dtype=np.uint8)
 t=Translation(TextBlock('Hello world',Box(10,20,200,30),.99,30),'नमस्ते')
 Controller.finished(s,4,SimpleNamespace(translations=[t],metrics={'total_ms':300}))
 assert painted and s.completed_generation==4
 assert s.caption_expires_at==s.last_submit+2

def test_expired_translation_is_cleared_without_new_result(monkeypatch):
 s,calls=state(monkeypatch);s.auto=False;s.overlay.items=[object()];s.caption_expires_at=monotonic()-1
 cleared=[];s.clear_visuals=lambda:cleared.append(True)
 Controller.tick(s)
 assert cleared and not calls

def test_caption_hold_preserves_old_translation_on_empty_result(monkeypatch):
 s,calls=state(monkeypatch)
 from dataclasses import replace
 s.config=replace(s.config,caption_hold=True)
 s.busy=True;s.last_submit=monotonic()-.2
 s.overlay.items=[object()]
 s.overlay.show_translations=lambda *args:(_ for _ in ()).throw(AssertionError('must retain prior caption'))
 s.capture.mapping=object()
 s.job_frame=np.zeros((110,900,3),dtype=np.uint8)
 Controller.finished(s,4,SimpleNamespace(translations=[],metrics={'total_ms':200}))
 assert len(s.overlay.items)==1

def test_caption_hold_preserves_old_translation_on_failure(monkeypatch):
 s,calls=state(monkeypatch)
 from dataclasses import replace
 s.config=replace(s.config,caption_hold=True)
 s.overlay.items=[object()]
 s.clear=lambda:(_ for _ in ()).throw(AssertionError('must retain prior caption'))
 messages=[];s.status=lambda message,**kwargs:messages.append(message)
 Controller.failed(s,4,'Network unavailable')
 assert len(s.overlay.items)==1 and 'keeping the previous' in messages[0]
