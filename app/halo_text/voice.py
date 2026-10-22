"""Approved online spoken output, bounded queue, in-memory audio and interruptible playback."""
import asyncio,io,json,logging
from queue import Queue,Empty,Full
from threading import Event
from time import monotonic
from PySide6.QtCore import QThread,Signal
from .paths import ROOT
log=logging.getLogger("halo")
CATALOG=ROOT/"runtime/cache/edge-voices.json"
ALIASES={"zh-CN":"zh-CN","zh-TW":"zh-TW","pt":"pt-BR","no":"nb","fil":"fil","tl":"fil","yue":"zh-HK"}
def voices_for(target,voices):
    locale=ALIASES.get(target,target).lower()
    return [v for v in voices if v.get("Locale","").lower()==locale or v.get("Locale","").lower().startswith(locale+"-")]
def cached_voices():
    try:
        data=json.loads(CATALOG.read_text(encoding="utf-8"))
        return data if isinstance(data,list) else []
    except (OSError,ValueError):return []
async def available_voices():
    cached=cached_voices()
    if cached:return cached
    import edge_tts
    voices=await asyncio.wait_for(edge_tts.list_voices(),15)
    CATALOG.parent.mkdir(parents=True,exist_ok=True)
    CATALOG.write_text(json.dumps(voices),encoding="utf-8")
    return voices
def select_voice(target,voices,name="",gender="Female"):
    choices=voices_for(target,voices)
    if not choices:raise RuntimeError("No online speech voice for this language. Translated subtitles still work.")
    return next((v for v in choices if v["ShortName"]==name),next((v for v in choices if v["Gender"]==gender),choices[0]))["ShortName"]
async def synthesize(text,voice,rate=50,pitch=0):
    import edge_tts
    chunks=[];size=0
    request=edge_tts.Communicate(text,voice,rate=f"{rate:+d}%",pitch=f"{pitch:+d}Hz",connect_timeout=8,receive_timeout=12)
    async for chunk in request.stream():
        if chunk["type"]=="audio":
            size+=len(chunk["data"])
            if size>4*1024*1024:raise RuntimeError("Speech response too large")
            chunks.append(chunk["data"])
    if not chunks:raise RuntimeError("Speech service returned no audio")
    return b"".join(chunks)
def output_devices():
    import pyaudiowpatch as pa
    with pa.PyAudio() as audio:
        wasapi=audio.get_host_api_info_by_type(pa.paWASAPI)["index"]
        return [{"index":i,"name":d["name"]} for i in range(audio.get_device_count())
                if (d:=audio.get_device_info_by_index(i))["maxOutputChannels"]>0 and d["hostApi"]==wasapi]
def play_audio(data,stop_event,device_index=-1,on_start=None):
    import av,pyaudiowpatch as pa
    audio=pa.PyAudio();stream=None
    try:
        device=audio.get_default_output_device_info() if device_index<0 else audio.get_device_info_by_index(device_index)
        if device["maxOutputChannels"]<1:raise RuntimeError("Selected output device has no speakers")
        rate=int(device["defaultSampleRate"])
        resampler=av.AudioResampler(format="s16",layout="mono",rate=rate)
        stream=audio.open(format=pa.paInt16,channels=1,rate=rate,output=True,output_device_index=device["index"],frames_per_buffer=rate//20)
        started=False
        with av.open(io.BytesIO(data)) as container:
            for frame in container.decode(audio=0):
                if stop_event.is_set():break
                for converted in resampler.resample(frame):
                    pcm=converted.to_ndarray().tobytes()
                    for pos in range(0,len(pcm),rate//20*2):
                        if stop_event.is_set():return
                        if not started:
                            started=True
                            if on_start:on_start()
                        stream.write(pcm[pos:pos+rate//20*2])
    finally:
        if stream is not None:
            stream.stop_stream();stream.close()
        audio.terminate()
class VoiceSession(QThread):
    state=Signal(str)
    failed=Signal(str)
    playback_started=Signal(float)
    def __init__(self,config,echo_gate,parent=None,ready_event=None):
        super().__init__(parent);self.config=config;self.echo_gate=echo_gate
        self.ready_event=ready_event or Event()
        self.stop_event=Event();self.queue=Queue(maxsize=1);self.loop=None;self.task=None
        self.discarded=0
    def enqueue(self,text,pitch_hz=0.0):
        if self.stop_event.is_set():return
        try:self.queue.put_nowait((monotonic(),text,pitch_hz))
        except Full:
            try:self.queue.get_nowait();self.discarded+=1
            except Empty:pass
            try:self.queue.put_nowait((monotonic(),text,pitch_hz))
            except Full:pass
    def stop(self):
        self.stop_event.set()
        loop,task=self.loop,self.task
        if loop is not None and task is not None:
            try:loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:pass
    def run_async(self,coroutine):
        self.loop=asyncio.new_event_loop()
        try:
            self.task=self.loop.create_task(asyncio.wait_for(coroutine,20))
            return self.loop.run_until_complete(self.task)
        finally:
            self.task=None
            try:self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            except Exception:pass
            self.loop.close();self.loop=None
    def notify_playback(self,started):
        delay=(monotonic()-started)*1000
        log.info("voice_metrics synthesis_to_play_ms=%.1f",delay)
        self.playback_started.emit(delay)

    def run(self):
        try:
            self.state.emit("Preparing selected voice...")
            from .voice_setup import installed as local_installed
            local=None
            if self.config.audio_local_voices and self.config.target=="hi" and local_installed():
                from .local_voice import LocalVoice
                local=LocalVoice(self.config.audio_cpu_threads)
                voice="Local Hindi (Pratham / Priyamvada)";voices=[]
            else:
                voices=self.run_async(available_voices())
                voice=select_voice(self.config.target,voices,self.config.audio_voice,self.config.audio_voice_gender)
            self.ready_event.set()
            self.state.emit("Ready: "+voice)
            while not self.stop_event.is_set():
                try:stamp,text,pitch_hz=self.queue.get(timeout=.1)
                except Empty:continue
                if monotonic()-stamp>6:continue
                self.state.emit("Generating spoken translation...")
                started=monotonic()
                chosen_voice=voice
                gender=self.config.audio_voice_gender
                shift=self.config.audio_voice_pitch
                if self.config.audio_match_voice_range and not self.config.audio_voice and pitch_hz>0:
                    gender="Female" if pitch_hz>=170 else "Male"
                    if local is None:chosen_voice=select_voice(self.config.target,voices,gender=gender)
                    reference=200 if gender=="Female" else 120
                    shift+=max(-20,min(20,round(pitch_hz-reference)))
                try:
                    data=(local.synthesize(text,gender,self.config.audio_voice_rate,shift) if local is not None else
                          self.run_async(synthesize(text,chosen_voice,self.config.audio_voice_rate,shift)))
                except asyncio.CancelledError:raise
                except Exception as exc:
                    if not self.stop_event.is_set():self.failed.emit("Speech request failed; subtitles continue. "+type(exc).__name__)
                    self.stop_event.wait(1)
                    continue
                if self.stop_event.is_set():break
                if monotonic()-stamp>(6 if local else 20):
                    self.state.emit("Skipped delayed speech; subtitles remain visible");continue
                if self.config.audio_feedback_guard:self.echo_gate.set()
                self.state.emit("Speaking (listening paused to prevent feedback)" if self.config.audio_feedback_guard else "Speaking")
                try:
                    play_audio(data,self.stop_event,self.config.audio_output_device,
                               on_start=lambda:self.notify_playback(started))
                finally:
                    self.stop_event.wait(.15);self.echo_gate.clear()
                self.state.emit("Ready: "+voice)
        except (asyncio.CancelledError,):pass
        except Exception as exc:
            log.warning("Voice output failed: %s",type(exc).__name__)
            if not self.stop_event.is_set():self.failed.emit("Voice unavailable; subtitles continue. "+type(exc).__name__)
        finally:
            self.echo_gate.clear();self.ready_event.set()
