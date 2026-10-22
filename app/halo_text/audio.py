"""Opt-in local English speech recognition and translated live subtitles."""
from dataclasses import replace
import logging
from queue import Queue,Empty,Full
from threading import Event
from time import monotonic
import numpy as np
from PySide6.QtCore import QThread,Signal
from .audio_core import SpeechSegmenter,subtitle_is_current,estimate_pitch
from .speech_setup import SPEECH_MODEL,installed
from .core import normalize

log=logging.getLogger("halo")

def decode_audio_file(path,sampling_rate=16000):
    """Decode locally with the installed PyAV API (no deprecated keyword arguments)."""
    import av
    resampler=av.AudioResampler(format="fltp",layout="mono",rate=sampling_rate)
    parts=[]
    with av.open(path) as container:
        for frame in container.decode(audio=0):
            parts.extend(converted.to_ndarray()[0] for converted in resampler.resample(frame))
        parts.extend(converted.to_ndarray()[0] for converted in resampler.resample(None))
    return np.concatenate(parts).astype(np.float32) if parts else np.empty(0,np.float32)

class SpeechEngine:
    def __init__(self,config):
        if not installed():
            raise RuntimeError("Speech model missing. Run: app/run.py --install-audio")
        from faster_whisper import WhisperModel
        from .translation import create_translator
        self.model=WhisperModel(str(SPEECH_MODEL),device="cpu",compute_type="int8",
                               cpu_threads=config.audio_cpu_threads,num_workers=1,local_files_only=True)
        self.translator=create_translator(replace(config,cpu_threads=config.audio_cpu_threads))
        # Exercise inference and the selected translator before opening capture.
        segments,_=self.model.transcribe(np.zeros(16000,np.float32),language="en",beam_size=1,
                                        vad_filter=False,without_timestamps=True,max_new_tokens=1)
        list(segments)
        if hasattr(self.translator.backend,"engine"):
            self.translator.translate_many(["Welcome to our project."])
        self.last_pitch_hz=0.0

    def transcribe(self,samples):
        if not len(samples) or float(np.max(np.abs(samples)))<.002:
            return ""
        segments,_=self.model.transcribe(
            samples,language="en",beam_size=1,temperature=0,
            max_new_tokens=80,repetition_penalty=1.1,no_repeat_ngram_size=3,
            condition_on_previous_text=False,without_timestamps=True,
            vad_filter=True,vad_parameters={"min_silence_duration_ms":200,"speech_pad_ms":100})
        return normalize(" ".join(segment.text for segment in segments
                                  if segment.no_speech_prob<.6 and segment.avg_logprob>-1.2))

    def process(self,samples):
        self.last_pitch_hz=estimate_pitch(samples)
        text=self.transcribe(samples)
        if not text or sum(c.isalpha() for c in text)<2:
            return None
        return text,self.translator.translate_many([text])[0]

class LiveAudio:
    """A callback captures; the consumer performs inference. Queue never grows unbounded."""
    def __init__(self,source,stop_event=None,echo_gate=None):
        if source not in ("system","microphone"):
            raise ValueError("Audio source must be system or microphone")
        import pyaudiowpatch as pa
        import av
        self.stop_event=stop_event or Event()
        self.echo_gate=echo_gate or Event()
        self.pa_module=pa
        self.audio=pa.PyAudio()
        self.stream=None
        self.queue=Queue(maxsize=10)
        self.dropped=0
        self.closed=False
        self.resampler=av.AudioResampler(format="fltp",layout="mono",rate=16000)
        self.av=av
        try:
            device=(self.audio.get_default_wasapi_loopback() if source=="system"
                    else self.audio.get_default_input_device_info())
            self.rate=int(device["defaultSampleRate"])
            self.channels=int(device["maxInputChannels"])
            if self.channels<1:
                raise RuntimeError("No input channels are available.")
            self.device_name=device["name"]
            self.stream=self.audio.open(format=pa.paInt16,channels=self.channels,rate=self.rate,
                                        input=True,input_device_index=device["index"],
                                        frames_per_buffer=max(1,self.rate//10),stream_callback=self.callback)
        except Exception:
            self.close()
            raise

    def callback(self,data,frame_count,time_info,status):
        if self.closed or self.stop_event.is_set():
            return None,self.pa_module.paComplete
        if self.echo_gate.is_set():
            return None,self.pa_module.paContinue
        item=(monotonic(),data)
        try:
            self.queue.put_nowait(item)
        except Full:
            try:
                self.queue.get_nowait()
            except Empty:
                pass
            self.dropped+=1
            try:
                self.queue.put_nowait(item)
            except Full:
                self.dropped+=1
        return None,self.pa_module.paContinue

    def read(self):
        try:
            stamp,data=self.queue.get(timeout=.2)
        except Empty:
            if self.stream is not None and not self.stream.is_active():
                raise RuntimeError("Audio device stopped. Stop subtitles and select the device again.")
            return None
        pcm=np.frombuffer(data,dtype=np.int16).reshape(-1,self.channels)
        mono=pcm.astype(np.float32).mean(axis=1)/32768.0
        frame=self.av.AudioFrame.from_ndarray(mono.reshape(1,-1),format="fltp",layout="mono")
        frame.sample_rate=self.rate
        frames=self.resampler.resample(frame)
        samples=np.concatenate([f.to_ndarray()[0] for f in frames]) if frames else np.empty(0,np.float32)
        return stamp,samples

    def close(self):
        self.closed=True
        if self.stream is not None:
            try:
                self.stream.stop_stream()
            finally:
                self.stream.close()
                self.stream=None
        if self.audio is not None:
            self.audio.terminate()
            self.audio=None

class AudioSession(QThread):
    state=Signal(str)
    subtitle=Signal(str,str,float)
    failed=Signal(str)

    def __init__(self,config,source,parent=None,echo_gate=None,output_ready=None):
        super().__init__(parent)
        self.config=config
        self.output_ready=output_ready
        self.source=source
        self.echo_gate=echo_gate or Event()
        self.stop_event=Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        capture=None
        try:
            self.state.emit("Loading speech model...")
            engine=SpeechEngine(self.config)
            if self.stop_event.is_set():
                return
            while self.output_ready is not None and not self.output_ready.is_set():
                if self.stop_event.wait(.1):return
            capture=LiveAudio(self.source,self.stop_event,self.echo_gate)
            self.state.emit("Listening to "+("system audio" if self.source=="system" else "microphone"))
            segmenter=SpeechSegmenter(threshold=self.config.audio_energy_threshold,
                                      max_seconds=self.config.audio_max_seconds)
            previous_drops=0
            while not self.stop_event.is_set():
                if self.echo_gate.is_set():
                    segmenter.reset()
                    while True:
                        try:capture.queue.get_nowait()
                        except Empty:break
                    self.stop_event.wait(.05)
                    continue
                item=capture.read()
                if item is None:
                    # Some loopback devices stop delivering buffers when playback ends.
                    # Supply endpoint silence so a short final phrase is still emitted.
                    if not segmenter.parts:continue
                    stamp,samples=monotonic(),np.zeros(3200,np.float32)
                else:
                    stamp,samples=item
                if capture.dropped!=previous_drops:
                    segmenter.reset()
                    previous_drops=capture.dropped
                    self.state.emit("Audio overloaded; catching up...")
                if monotonic()-stamp>1.0:
                    segmenter.reset()
                    continue
                utterance=segmenter.feed(samples)
                if utterance is None:
                    continue
                started=monotonic()
                result=engine.process(utterance)
                elapsed=monotonic()-started
                log.info("audio_metrics seconds=%.2f processing_ms=%.1f dropped_chunks=%d",
                         len(utterance)/16000,elapsed*1000,capture.dropped)
                if self.stop_event.is_set():
                    break
                if result and subtitle_is_current(stamp,monotonic(),max_age=6.0):
                    self.subtitle.emit(*result,engine.last_pitch_hz)
                    self.state.emit("Listening to "+("system audio" if self.source=="system" else "microphone"))
        except Exception as exc:
            log.warning("Audio subtitles failed: %s",type(exc).__name__)
            if not self.stop_event.is_set():
                self.failed.emit(str(exc)[:240])
        finally:
            if capture is not None:
                capture.close()

def device_summary():
    """Enumerates device metadata only; does not open a recording stream."""
    import pyaudiowpatch as pa
    with pa.PyAudio() as audio:
        result={}
        for source,getter in (("system",audio.get_default_wasapi_loopback),
                              ("microphone",audio.get_default_input_device_info)):
            try:
                item=getter()
                result[source]={"available":True,"name":item["name"],"rate":item["defaultSampleRate"],
                                "channels":item["maxInputChannels"]}
            except Exception as exc:
                result[source]={"available":False,"message":str(exc)}
        return result
