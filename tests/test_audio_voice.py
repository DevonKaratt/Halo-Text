from threading import Event
from types import SimpleNamespace
from queue import Queue
import numpy as np
import pytest
from halo_text.audio_core import SpeechSegmenter,estimate_pitch,subtitle_is_current
from halo_text.audio import LiveAudio
from halo_text.voice import VoiceSession,voices_for,select_voice
from halo_text.config import Config

def test_short_phrase_endpoint_and_silence_rejection():
 segmenter=SpeechSegmenter()
 voice=np.full(1600,.1,dtype=np.float32);silence=np.zeros(1600,np.float32)
 for _ in range(4):assert segmenter.feed(voice) is None
 assert segmenter.feed(silence) is None
 assert segmenter.feed(silence) is None
 result=segmenter.feed(silence)
 assert result is not None and len(result)==11200
 for _ in range(8):assert segmenter.feed(silence) is None

def test_continuous_speech_is_bounded_by_maximum_chunk():
 segmenter=SpeechSegmenter(max_seconds=1)
 voice=np.full(1600,.1,dtype=np.float32)
 results=[segmenter.feed(voice) for _ in range(20)]
 assert sum(r is not None for r in results)==2

def test_pitch_range_is_approximate_and_silence_has_no_pitch():
 t=np.arange(16000)/16000
 for hz in [120,220]:assert abs(estimate_pitch((.1*np.sin(2*np.pi*hz*t)).astype(np.float32))-hz)<8
 assert estimate_pitch(np.zeros(16000,np.float32))==0

def test_feedback_gate_discards_captured_audio():
 gate=Event();gate.set()
 capture=SimpleNamespace(closed=False,stop_event=Event(),echo_gate=gate,queue=Queue(1),pa_module=SimpleNamespace(paComplete=1,paContinue=0))
 assert LiveAudio.callback(capture,b'pcm',1600,None,0)==(None,0)
 assert capture.queue.empty()

def test_voice_queue_keeps_only_latest_pending_phrase(qapp):
 session=VoiceSession(Config(),Event())
 session.enqueue('old');session.enqueue('new',150)
 assert session.queue.qsize()==1 and session.queue.get()[1:] == ('new',150)
 assert session.discarded==1
 session.stop();session.enqueue('ignored');assert session.queue.empty()

def test_voice_selection_never_uses_wrong_target_language():
 voices=[{'ShortName':'en-US-A','Locale':'en-US','Gender':'Female'},{'ShortName':'hi-IN-B','Locale':'hi-IN','Gender':'Male'}]
 assert select_voice('hi',voices,name='en-US-A')=='hi-IN-B'
 with pytest.raises(RuntimeError):select_voice('brx',voices)

def test_playback_error_always_releases_feedback_gate(qapp,monkeypatch):
 import halo_text.voice as module
 async def catalog():return [{'ShortName':'hi-IN-A','Locale':'hi-IN','Gender':'Female'}]
 async def synth(*args):return b'audio'
 def fail(*args,**kwargs):raise RuntimeError('Device disconnected')
 monkeypatch.setattr(module,'available_voices',catalog);monkeypatch.setattr(module,'synthesize',synth);monkeypatch.setattr(module,'play_audio',fail)
 gate=Event();session=VoiceSession(Config(audio_local_voices=False),gate)
 session.enqueue('नमस्ते');errors=[];session.failed.connect(errors.append)
 session.run()
 assert errors and not gate.is_set()

def test_audio_age_rejects_future_or_old_chunks():
 assert not subtitle_is_current(10,9)
 assert not subtitle_is_current(0,7,max_age=6)
 assert subtitle_is_current(0,1,max_age=6)


def test_stop_cancels_pending_online_voice_request(qapp,monkeypatch):
 import asyncio,time
 from PySide6.QtTest import QTest
 import halo_text.voice as module
 started=Event()
 async def catalog():return [{'ShortName':'hi-IN-A','Locale':'hi-IN','Gender':'Female'}]
 async def slow(*args):
  started.set();await asyncio.sleep(60);return b'audio'
 monkeypatch.setattr(module,'available_voices',catalog);monkeypatch.setattr(module,'synthesize',slow)
 session=VoiceSession(Config(audio_local_voices=False),Event());session.enqueue('नमस्ते');session.start()
 deadline=time.monotonic()+5
 while not started.is_set() and time.monotonic()<deadline:QTest.qWait(10)
 try:
  assert started.is_set()
  session.stop();assert session.wait(2000)
 finally:
  session.stop();session.wait(5000)

def test_spoken_output_defaults_to_one_point_five_speed():
 assert Config().audio_voice_rate==50

def test_telugu_restoration_preserves_numbers_and_names():
 from halo_text.indic_translation import restore_telugu_script
 assert restore_telugu_script('दयचेसि तलुपु मूसिवेयंडि.')=='దయచేసి తలుపు మూసివేయండి.'
 assert restore_telugu_script('25 minutes')=='25 minutes'


def test_tamil_restoration_keeps_latin_numbers_and_uses_tamil_script():
    from halo_text.indic_translation import restore_tamil_script
    output=restore_tamil_script("रयिल् तामतमाकिविट्टतु . 25 minutes")
    assert any("\u0b80"<=char<="\u0bff" for char in output)
    assert not any("\u0900"<=char<="\u097f" for char in output)
    assert "25 minutes" in output

def test_tamil_uses_installed_indic_pack(monkeypatch):
    from halo_text import online,model_setup
    from halo_text.config import Config
    monkeypatch.setattr(model_setup,"find_model",lambda target:None)
    monkeypatch.setattr("halo_text.indic_setup.installed",lambda:True)
    assert online.route(Config(target="ta",backend="auto"))=="indic"
    assert online.route(Config(target="ta",backend="local"))=="indic"
