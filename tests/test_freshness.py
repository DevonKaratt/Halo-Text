"""Regression: a completed AI result must not repaint a paused or changed screen."""
from types import SimpleNamespace
import numpy as np
from halo_text.core import Box, frame_signature
from halo_text.app import Controller
from halo_text.pipeline import PipelineResult

class FakeOverlay:
    def __init__(self): self.calls = 0
    def show_translations(self,*args):
        self.calls += 1
        return 0,0

class Harness:
    finished = Controller.finished
    def __init__(self):
        self.ready = True
        self.busy = True
        self.exiting = False
        self.generation = 2
        self.selector = None
        self.auto = False
        self.overlay = FakeOverlay()
        self.region = Box(0,0,100,100)
        self.frame = np.full((100,100,3),255,np.uint8)
        self.signature = frame_signature(self.frame)
        self.job_frame = self.frame.copy()
        self.capture = SimpleNamespace(grab=lambda region:self.frame,mapping=None)
        self.config = SimpleNamespace(backend="local")
    def status(self,*args,**kwargs): pass

def result():
    return PipelineResult([],{"total_ms":30})

def test_result_from_before_clear_or_new_selection_never_paints(monkeypatch):
    monkeypatch.setattr("halo_text.app.desktop_available",lambda:True)
    h = Harness()
    h.finished(1,result())
    assert h.overlay.calls == 0 and not h.busy

def test_last_moment_screen_change_never_paints(monkeypatch):
    monkeypatch.setattr("halo_text.app.desktop_available",lambda:True)
    h = Harness()
    h.frame[20:50,20:50] = 0
    h.finished(2,result())
    assert h.overlay.calls == 0

def test_locked_desktop_never_paints(monkeypatch):
    monkeypatch.setattr("halo_text.app.desktop_available",lambda:False)
    h = Harness()
    h.finished(2,result())
    assert h.overlay.calls == 0

def test_current_result_can_paint(monkeypatch):
    monkeypatch.setattr("halo_text.app.desktop_available",lambda:True)
    h = Harness()
    h.finished(2,result())
    assert h.overlay.calls == 1


def test_old_job_failure_does_not_cancel_new_request():
    h=Harness()
    h.wanted=True
    h.auto=True
    def must_not_clear():
        raise AssertionError("Old failure cancelled the new request")
    h.clear=must_not_clear
    Controller.failed(h,1,"old request failed")
    assert h.wanted and h.auto and not h.busy

def test_tiny_last_moment_text_change_never_paints(monkeypatch):
    from halo_text.core import TextBlock, frames_differ
    from halo_text.pipeline import Translation
    monkeypatch.setattr("halo_text.app.desktop_available",lambda:True)
    h=Harness()
    h.frame=np.full((2160,3840,3),255,np.uint8)
    h.job_frame=h.frame.copy()
    h.signature=frame_signature(h.frame)
    h.frame[100:104,100:104]=0
    assert not frames_differ(h.signature,frame_signature(h.frame))
    block=TextBlock("Test",Box(80,80,300,40),1,20)
    output=PipelineResult([Translation(block,"परीक्षण")],{"total_ms":30})
    h.finished(2,output)
    assert h.overlay.calls==0 and h.job_frame is None
