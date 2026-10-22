"""Opt-in native audio test using a generated English phrase; no recording is saved."""
from pathlib import Path
import sys,json
from threading import Thread,Event
from time import monotonic
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
from halo_text.paths import ROOT,configure
configure()
from halo_text.pipeline import preload_runtime
preload_runtime()
from halo_text.windows import enable_dpi_awareness
enable_dpi_awareness()
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,QEventLoop,QObject,Slot
from halo_text.fonts import load_fonts
from halo_text.config import Config
from halo_text.app import Controller
from halo_text.voice import play_audio
from halo_text.audio import decode_audio_file
from queue import Empty
import numpy as np
import halo_text.audio as audio_module
app=QApplication([]);app.setQuitOnLastWindowClosed(False);load_fonts()
source_go=Event()
class FixtureCapture:
 def __init__(self,source,stop_event=None,echo_gate=None):
  self.stop_event=stop_event;self.echo_gate=echo_gate;self.samples=decode_audio_file(str(ROOT/'reports/audio/generated_english_1.mp3'))
  self.dropped=0;self.position=0
  self.queue=__import__('queue').Queue()
 def read(self):
  if self.stop_event.wait(.1) or not source_go.is_set():return None
  if self.echo_gate.is_set():return None
  chunk=self.samples[self.position:self.position+1600]
  self.position+=1600
  if not len(chunk):chunk=np.zeros(1600,np.float32)
  return monotonic(),chunk
 def close(self):pass
audio_module.LiveAudio=FixtureCapture
controller=None;audio_states=[];voice_states=[];play_starts=[];matched=[];subtitles=[];began=0;capture_errors=[];seen=[]
class SimplePlayer:
 def is_alive(self):return False
class Observer(QObject):
 @Slot(str)
 def audio_state(self,text):audio_states.append(text)
 @Slot(str)
 def voice_state(self,text):voice_states.append(text)
 @Slot(float)
 def playback(self,delay):play_starts.append({'synthesis_to_first_pcm_ms':round(delay,1),'since_source_start_ms':round((monotonic()-began)*1000,1),'feedback_gate_active':controller.echo_gate.is_set()})
 @Slot(str,str,float)
 def subtitle(self,english,translated,pitch):
  subtitles.append(monotonic());seen.append(english)
  if 'please close the door' in english.lower():matched.append({'english_matched':True,'translated_nonempty':bool(translated),'pitch_hz':round(pitch,1),'since_source_start_ms':round((monotonic()-began)*1000,1)})
observer=Observer()
def wait_for(predicate,seconds=45):
 deadline=monotonic()+seconds;loop=QEventLoop();timer=QTimer();timer.setInterval(20)
 timer.timeout.connect(lambda:loop.quit() if predicate() or monotonic()>deadline else None)
 timer.start();loop.exec();timer.stop()
 if not predicate():raise RuntimeError('Audio native timeout: '+str(audio_states[-3:])+' / '+str(voice_states[-3:])+' / recognized_count: '+str(len(seen))+' / errors: '+str(capture_errors))
def pause(ms):
 loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
try:
 controller=Controller(app,Config(audio_spoken=True,audio_local_voices=True,audio_match_voice_range=True))
 wait_for(lambda:controller.ready)
 assert not controller.hotkeys.failures
 controller.toggle_audio('system')
 controller.audio_session.state.connect(observer.audio_state)
 controller.audio_session.failed.connect(capture_errors.append)
 controller.audio_session.subtitle.connect(observer.subtitle)
 controller.voice_session.state.connect(observer.voice_state)
 controller.voice_session.playback_started.connect(observer.playback)
 wait_for(lambda:any(s.startswith('Listening') for s in audio_states) and any(s.startswith('Ready: Local') for s in voice_states),60)
 began=monotonic();player=SimplePlayer();source_go.set()
 wait_for(lambda:bool(matched) or bool(capture_errors),20)
 assert not capture_errors,capture_errors
 wait_for(lambda:bool(play_starts),20)
 wait_for(lambda:not controller.echo_gate.is_set() and not player.is_alive(),20)
 count=len(subtitles);pause(1500)
 assert len(subtitles)==count,'Unexpected new recognition after generated speech playback; possible feedback'
 started=monotonic();controller.stop_audio()
 wait_for(lambda:controller.audio_session is None and controller.voice_session is None,15)
 report={'scope':'Generated English injected at 100 ms real-time intervals into AudioSession instead of recording system audio; local recognition/Hindi translation and real speaker playback. Verifies the controlled pipeline and feedback gating, not live loopback transcription accuracy. No microphone speech or captured audio saved.','matched_phrase':matched,'playback':play_starts,'feedback_gate_engaged_during_playback':all(p['feedback_gate_active'] for p in play_starts),'stop_threads_ms':round((monotonic()-started)*1000,1),'audio_overlay_capture_excluded':True,'hotkey_conflicts':controller.hotkeys.failures}
 (ROOT/'reports/audio/native.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2),flush=True)
finally:
 if controller:
  controller.quit();wait_for(lambda:not controller.thread.isRunning() and controller.audio_session is None and controller.voice_session is None,30)
  app.processEvents()
