from types import SimpleNamespace
import numpy as np
from halo_text.config import Config
from halo_text.core import Box,TextBlock


def test_caption_sentences_reuse_unchanged_part(monkeypatch):
    from halo_text import pipeline as module
    class Reader:
        last_source="en"
        def recognize(self,image,fast_captions=False):
            return [TextBlock(image,Box(0,0,300,30),.99,30)]
    calls=[]
    class Translator:
        def translate_many(self,texts):
            calls.append(texts)
            return ["translated:"+text for text in texts]
    monkeypatch.setattr(module,"ScreenOCR",lambda config:Reader())
    from halo_text.translation import CachedTranslator
    monkeypatch.setattr(module,"create_translator",lambda config:CachedTranslator(Translator()))
    pipe=module.Pipeline(Config(target="hi",input_language="en"))
    first=pipe.process("Hello. The train is late.",fast_captions=True)
    second=pipe.process("Hello. The train is here.",fast_captions=True)
    assert calls==[["Hello.","The train is late."],["The train is here."]]
    assert first.translations[0].text.startswith("translated:Hello.")
    assert second.translations[0].text.endswith("translated:The train is here.")


def test_approximate_voice_labels():
    from halo_text.audio_core import ApproximateVoiceLabels
    tracker=ApproximateVoiceLabels()
    assert tracker.label(120)=="Voice 1 (approx.)"
    assert tracker.label(130)=="Voice 1 (approx.)"
    assert tracker.label(230)=="Voice 2 (approx.)"
    assert tracker.label(0)=="Voice"


def test_window_follow_updates_box(monkeypatch):
    from halo_text.app import Controller
    monkeypatch.setattr("halo_text.windows.window_rect",lambda hwnd:(120,80,1000,700))
    state=SimpleNamespace(config=Config(),follow_binding=(55,(.1,.2,.4,.1)),
        region=Box(100,100,400,70),capture=SimpleNamespace(mapping=SimpleNamespace(left=0,top=0,width=1920,height=1080)),
        invalidate=lambda:None,show_outline=lambda:None,wanted=False)
    Controller.update_followed_region(state)
    assert state.region==Box(220,220,400,70)
    assert state.wanted
