"""Background coordinator: Qt owns windows; one worker owns all AI models."""
import json
import os
import sys
import logging
import numpy as np
from dataclasses import replace
from logging.handlers import RotatingFileHandler
from time import monotonic
from threading import Event
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot, QLockFile, Qt, QProcess
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap, QCursor
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QMessageBox
from .capture import ScreenCapture
from .config import load_config
from .core import Box, frame_signature, frames_differ, text_regions_differ
from .overlay import Overlay, RegionSelector
from .outline import SelectionOutline
from .floating import FloatingHalo
from .paths import STATE,ROOT
from .languages import LANGUAGES, language
from .model_setup import find_model
from .online import route
from .windows import desktop_available, hotkey_filter, require_windows

log = logging.getLogger("halo")

def model_command(*arguments):
    """Run the same installer from source Python or the portable executable."""
    return (sys.executable,list(arguments)) if getattr(sys,"frozen",False) else (sys.executable,[str(ROOT/"app/run.py"),*arguments])

class Worker(QObject):
    ready = Signal()
    result = Signal(int, object)
    failed = Signal(int, str)
    language_ready = Signal(object)
    language_failed = Signal(str)
    ocr_dropped = Signal(str)
    benchmark_ready = Signal(object)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.pipeline = None

    @Slot()
    def initialize(self):
        try:
            log.info("Loading pipeline in background worker")
            from .pipeline import Pipeline
            log.info("Constructing OCR and translation engines")
            self.pipeline = Pipeline(self.config)
            log.info("Warming OCR")
            self.pipeline.warmup()
            log.info("Worker ready")
            self.ready.emit()
        except Exception as exc:
            log.exception("Model initialization failed")
            self.failed.emit(-1, str(exc))

    @Slot(object)
    def change_language(self, config):
        try:
            from .translation import create_translator
            replacement = create_translator(config)
            # Verify the new engine before replacing the working language.
            if hasattr(getattr(replacement, "backend", None), "engine"):
                replacement.translate_many(["Welcome to our project."])
            self.pipeline.translator = replacement
            if hasattr(self.pipeline,"source_translators"):
                self.pipeline.source_translators.clear()
            if hasattr(self.pipeline,"ocr"):
                self.pipeline.ocr.reload_packs()
                self.pipeline.ocr.config = config
            if hasattr(self.pipeline,"config"):
                self.pipeline.config = config
            self.config = config
            self.language_ready.emit(config)
        except Exception:
            log.exception("Language switch failed")
            self.language_failed.emit("Could not load the language. The previous language is still selected.")

    @Slot(int, object, bool)
    def process(self, generation, frame, fast_captions=False):
        try:
            if self.pipeline is None:
                raise RuntimeError("Models are not ready.")
            result = self.pipeline.process(frame,fast_captions=fast_captions)
            self.result.emit(generation, result)
        except Exception as exc:
            log.warning("Translation failed: %s",type(exc).__name__)
            self.failed.emit(generation, str(exc))

    @Slot(str,str,str)
    def choose_source_route(self, source, target, choice):
        if self.pipeline is not None:
            self.pipeline.source_routes[source,target]=choice

    @Slot(str)
    def drop_ocr(self,key):
        if self.pipeline is not None:
            self.pipeline.ocr.pack_engines.pop(key,None)
        self.ocr_dropped.emit(key)

    @Slot(object)
    def benchmark(self,frame):
        from time import perf_counter
        try:
            if frame is None:
                import cv2
                frame=np.full((100,700,3),245,np.uint8)
                cv2.putText(frame,"Welcome to HALO TEXT",(12,68),
                            cv2.FONT_HERSHEY_SIMPLEX,1.25,(20,20,20),2,cv2.LINE_AA)
            times=[]
            for _ in range(3):
                started=perf_counter()
                self.pipeline.ocr.recognize(frame,fast_captions=self.config.fast_captions)
                times.append((perf_counter()-started)*1000)
            translation_ms=None
            if route(self.config) in {"local","indic"}:
                samples=[]
                for phrase in ("The meeting starts tomorrow morning.",
                               "Please check the latest information."):
                    started=perf_counter()
                    self.pipeline.translator.backend.translate_many([phrase])
                    samples.append((perf_counter()-started)*1000)
                translation_ms=round(min(samples))
            import onnxruntime as ort
            self.benchmark_ready.emit({"ocr_ms":round(sorted(times)[1]),
                "translation_ms":translation_ms,
                "image":(frame.shape[1],frame.shape[0]),
                "directml_available":"DmlExecutionProvider" in ort.get_available_providers(),
                "threads":self.config.cpu_threads})
        except Exception as exc:
            self.benchmark_ready.emit({"error":str(exc)[:180]})

def make_icon():
    pixmap = QPixmap(64,64)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#2563eb"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(3,3,58,58,15,15)
    font = QFont("Segoe UI")
    font.setPixelSize(36)
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("white"))
    p.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "H")
    p.end()
    return QIcon(pixmap)

class Controller(QObject):
    request_job = Signal(int, object, bool)
    request_language = Signal(object)
    request_source_route = Signal(str,str,str)
    request_drop_ocr = Signal(str)
    request_benchmark = Signal(object)

    def __init__(self, application, config):
        super().__init__()
        self.application, self.config = application, config
        self.screen = application.primaryScreen()
        self.capture = ScreenCapture(self.screen)
        self.overlay = Overlay(self.screen, config)
        if not self.overlay.excluded:
            self.capture.close()
            raise RuntimeError("Windows could not exclude the overlay from screen capture. "
                               "Use a normal desktop session on Windows 10 (2004+) or Windows 11.")
        self.outline = SelectionOutline(self.screen)
        if not self.outline.excluded:
            self.capture.close()
            raise RuntimeError("Windows could not exclude the selection border from capture.")
        self.resume_after_language = False
        self.region = None
        self.follow_binding = None
        self.display_pending = False
        self.selector = None
        self.signature = None
        self.job_frame = None
        self.caption_frame = None
        self.detected_source = "en"
        self.displayed_frame = None
        self.displayed_boxes = []
        self.changed_at = monotonic()
        self.last_submit = 0.0
        self.caption_expires_at = 0.0
        self.generation = 0
        self.completed_generation = -1
        self.busy = False
        self.ready = False
        self.load_error = None
        self.initializing = True
        self.wanted = False
        self.auto = False
        self.exiting = False
        self.audio_session = None
        self.model_download = None
        self.model_log_timer = QTimer(self)
        self.model_log_timer.setInterval(500)
        self.model_log_timer.timeout.connect(self.poll_model_download_log)
        self.model_log_offset = 0
        self.last_download_line = ""
        self.online_retry_after = 0.0
        self.voice_session = None
        self.voice_restart_pending = False
        self.echo_gate = Event()
        self.voice_ready = Event()
        self.audio_overlay = None
        self.audio_enabled = False
        self.audio_status = "Off"
        from .audio_core import ApproximateVoiceLabels
        self.voice_labels=ApproximateVoiceLabels()
        self.audio_display_token=0
        self.controls_depth = 0
        self.resume_after_controls = False
        self.floating = None
        self.tray = QSystemTrayIcon(make_icon(), application)
        self.menu = QMenu()
        self.status_action = self.menu.addAction("Loading OCR and translation model...")
        self.status_action.setEnabled(False)
        self.menu.addSeparator()
        self.control_actions = {}
        for title, name in (
                ("Translate now    Ctrl+Alt+T", "translate"),
                ("Choose screen area    Ctrl+Alt+R", "region"),
                ("Translate screen under pointer    Ctrl+Alt+F", "screen")):
            action = self.menu.addAction(title)
            action.triggered.connect(lambda checked=False, n=name: self.dispatch(n))
            self.control_actions[name] = action
        self.monitor_menu = self.menu.addMenu("Choose display")
        self.monitor_menu.aboutToShow.connect(self.populate_monitors)
        self.language_menu = self.menu.addMenu("Translation language")
        self.language_menu.aboutToShow.connect(self.populate_languages)
        self.input_menu = self.menu.addMenu("Input language")
        self.input_menu.aboutToShow.connect(self.populate_input_languages)
        self.download_action=self.menu.addAction("Download offline model for selected language",self.download_model)
        self.models_menu=self.menu.addMenu("Downloaded language models")
        self.models_menu.aboutToShow.connect(self.populate_downloaded_models)
        self.ocr_menu=self.menu.addMenu("Input OCR language packs")
        self.ocr_menu.aboutToShow.connect(self.populate_ocr_packs)
        self.original_action = QAction("Show original text    Ctrl+Alt+O", self.menu)
        self.original_action.setCheckable(True)
        self.original_action.triggered.connect(lambda: self.dispatch("original"))
        self.menu.addAction(self.original_action)
        self.auto_action = QAction("Watch selected area after scrolling    Ctrl+Alt+A", self.menu)
        self.auto_action.setCheckable(True)
        self.auto_action.triggered.connect(lambda: self.dispatch("auto"))
        self.menu.addAction(self.auto_action)
        self.caption_action = QAction("Faster captions (select only the subtitle strip)",self.menu)
        self.caption_action.setCheckable(True)
        self.caption_action.setChecked(config.fast_captions)
        self.caption_action.triggered.connect(self.set_fast_captions)
        self.menu.addAction(self.caption_action)
        self.caption_hold_action=QAction("Keep last caption until replacement",self.menu)
        self.caption_hold_action.setCheckable(True)
        self.caption_hold_action.setChecked(config.caption_hold)
        self.caption_hold_action.triggered.connect(lambda enabled:self.set_visual_option("caption_hold",enabled))
        self.menu.addAction(self.caption_hold_action)
        self.follow_action=QAction("Follow selected window when it moves or resizes",self.menu)
        self.follow_action.setCheckable(True)
        self.follow_action.setChecked(config.follow_window)
        self.follow_action.triggered.connect(lambda enabled:self.set_visual_option("follow_window",enabled))
        self.menu.addAction(self.follow_action)
        self.performance_action=self.menu.addAction("Check speed on this computer",self.check_performance)
        self.clear_action = self.menu.addAction("Clear and pause    Ctrl+Alt+C", lambda: self.dispatch("clear"))
        self.menu.addSeparator()
        self.audio_status_action = self.menu.addAction("Audio: off")
        self.audio_status_action.setEnabled(False)
        self.audio_menu = self.menu.addMenu("Audio translation and voice")
        self.audio_actions = {}
        for source,title in (("system","System audio (videos, meetings)"),
                             ("microphone","Microphone")):
            action = self.audio_menu.addAction(title)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False,selected=source:self.toggle_audio(selected))
            self.audio_actions[source] = action
        self.audio_menu.addSeparator()
        self.spoken_action=self.audio_menu.addAction("Speak translated audio (local or Microsoft voices)")
        self.spoken_action.setCheckable(True);self.spoken_action.setChecked(config.audio_spoken)
        self.spoken_action.triggered.connect(lambda enabled:self.set_audio_option("audio_spoken",enabled))
        self.audio_mode_menu=self.audio_menu.addMenu("Audio output mode")
        self.audio_mode_actions={}
        for label,spoken,subtitles in (("Subtitles and speech",True,True),
                                       ("Subtitles only",False,True),
                                       ("Speech only",True,False)):
            action=self.audio_mode_menu.addAction(label)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False,s=spoken,t=subtitles:self.set_audio_mode(s,t))
            self.audio_mode_actions[spoken,subtitles]=action
        self.speaker_action=self.audio_menu.addAction("Approximate voice labels on subtitles")
        self.speaker_action.setCheckable(True)
        self.speaker_action.setChecked(config.audio_speaker_labels)
        self.speaker_action.triggered.connect(lambda enabled:self.set_audio_option("audio_speaker_labels",enabled))
        self.subtitle_delay_menu=self.audio_menu.addMenu("Subtitle display delay")
        self.subtitle_delay_actions={}
        for value in (0,250,500,1000,2000,3000):
            action=self.subtitle_delay_menu.addAction(f"{value/1000:g} seconds")
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False,v=value:self.set_audio_option("audio_subtitle_delay_ms",v))
            self.subtitle_delay_actions[value]=action
        self.sync_audio_controls()
        self.voice_status_action=self.audio_menu.addAction("Voice: off");self.voice_status_action.setEnabled(False)
        self.local_voice_action=self.audio_menu.addAction("Prefer installed offline voices (if downloaded)")
        self.local_voice_action.setCheckable(True);self.local_voice_action.setChecked(config.audio_local_voices)
        self.local_voice_action.triggered.connect(lambda enabled:self.set_audio_option("audio_local_voices",enabled))
        self.match_voice_action=self.audio_menu.addAction("Approximate speaker pitch range (not voice cloning)")
        self.match_voice_action.setCheckable(True);self.match_voice_action.setChecked(config.audio_match_voice_range)
        self.match_voice_action.triggered.connect(lambda enabled:self.set_audio_option("audio_match_voice_range",enabled))
        self.voice_menu=self.audio_menu.addMenu("Choose voice for output language")
        self.voice_menu.aboutToShow.connect(self.populate_voices)
        self.voice_rate_menu=self.audio_menu.addMenu("Speaking speed")
        self.voice_rate_actions={}
        for title,value in (("1× normal",0),("1.25×",25),("1.5× recommended",50),("1.6×",60)):
            action=self.voice_rate_menu.addAction(title)
            action.setCheckable(True);action.setChecked(value==config.audio_voice_rate)
            self.voice_rate_actions[value]=action
            action.triggered.connect(lambda checked=False,v=value:self.set_audio_option("audio_voice_rate",v))
        self.voice_pitch_menu=self.audio_menu.addMenu("Voice pitch")
        for title,value in (("Lower",-10),("Normal",0),("Higher",10)):
            action=self.voice_pitch_menu.addAction(title)
            action.triggered.connect(lambda checked=False,v=value:self.set_audio_option("audio_voice_pitch",v))
        self.voice_output_menu=self.audio_menu.addMenu("Speech output device")
        self.voice_output_menu.aboutToShow.connect(self.populate_voice_outputs)
        self.feedback_action=self.audio_menu.addAction("Prevent feedback: pause listening while speaking")
        self.feedback_action.setCheckable(True);self.feedback_action.setChecked(config.audio_feedback_guard)
        self.feedback_action.triggered.connect(lambda enabled:self.set_audio_option("audio_feedback_guard",enabled))
        self.audio_menu.addAction("Stop listening and speech    Ctrl+Alt+S",self.stop_audio)
        self.menu.addSeparator()
        self.help_action = self.menu.addAction("Controls / shortcuts",self.show_help)
        self.floating_action = QAction("Show floating HALO icon",self.menu)
        self.floating_action.setCheckable(True)
        self.floating_action.triggered.connect(self.set_floating_visible)
        self.menu.addAction(self.floating_action)
        self.exit_action = self.menu.addAction("Exit    Ctrl+Alt+Q", lambda: self.dispatch("quit"))
        self.floating = FloatingHalo(application)
        self.floating.controls_requested.connect(self.open_floating_controls)
        self.floating.select_requested.connect(self.choose_region)
        self.floating.exclusion_failed.connect(self.floating_unavailable)
        self.build_floating_controls()
        for root_menu in (self.menu,self.floating_menu):
            root_menu.aboutToShow.connect(self.begin_controls)
            root_menu.aboutToHide.connect(self.end_controls)
        self.set_floating_visible(config.floating_icon)
        self.update_floating()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()
        self.hotkeys = hotkey_filter(self.dispatch)
        application.installNativeEventFilter(self.hotkeys)
        self.thread = QThread(self)
        self.worker = Worker(config)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.initialize)
        self.request_job.connect(self.worker.process)
        self.request_language.connect(self.worker.change_language)
        self.request_source_route.connect(self.worker.choose_source_route)
        self.request_drop_ocr.connect(self.worker.drop_ocr)
        self.request_benchmark.connect(self.worker.benchmark)
        self.worker.benchmark_ready.connect(self.show_performance)
        self.worker.ocr_dropped.connect(self.ocr_dropped)
        self.worker.language_ready.connect(self.language_ready)
        self.worker.language_failed.connect(self.language_failed)
        self.worker.ready.connect(self.models_ready)
        self.worker.result.connect(self.finished)
        self.worker.failed.connect(self.failed)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.finish_exit)
        self.thread.start()
        self.timer = QTimer(self)
        self.timer.setInterval(config.watch_timing()[0])
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.bind_screen_signals()
        application.screenAdded.connect(self.display_changed)
        application.screenRemoved.connect(self.display_changed)
        application.primaryScreenChanged.connect(self.display_changed)

    def status(self, text, notify=False):
        self.last_status = text
        self.status_action.setText(text)
        self.update_floating()
        source_name=LANGUAGES[self.detected_source].name if self.detected_source in LANGUAGES else self.detected_source
        self.tray.setToolTip((f"HALO TEXT | {source_name} > {language(self.config.target).name}\n" + text)[:127])
        if notify:
            self.tray.showMessage("HALO TEXT", text, QSystemTrayIcon.MessageIcon.Information, 4500)

    def build_floating_controls(self):
        self.floating_menu = QMenu(self.floating)
        self.floating_header = self.floating_menu.addAction("HALO TEXT")
        self.floating_header.setEnabled(False)
        self.floating_status = self.floating_menu.addAction("Loading...")
        self.floating_status.setEnabled(False)
        self.floating_menu.addSeparator()
        for name in ("region","translate","screen"):
            self.floating_menu.addAction(self.control_actions[name])
        self.floating_menu.addAction(self.auto_action)
        self.floating_menu.addAction(self.caption_action)
        self.floating_menu.addAction(self.caption_hold_action)
        self.floating_menu.addAction(self.follow_action)
        self.floating_menu.addAction(self.performance_action)
        self.floating_menu.addAction(self.original_action)
        self.floating_menu.addAction(self.clear_action)
        self.floating_menu.addSeparator()
        self.floating_menu.addMenu(self.language_menu)
        self.floating_menu.addMenu(self.input_menu)
        self.floating_menu.addAction(self.download_action)
        self.floating_menu.addMenu(self.models_menu)
        self.floating_menu.addMenu(self.ocr_menu)
        self.floating_menu.addMenu(self.monitor_menu)
        self.floating_menu.addMenu(self.audio_menu)
        self.floating_menu.addSeparator()
        self.floating_menu.addAction(self.help_action)
        self.floating_menu.addAction("Hide floating icon",lambda:self.set_floating_visible(False))
        self.floating_menu.addAction(self.exit_action)

    def update_floating(self):
        floating=getattr(self,"floating",None)
        if floating is None:
            return
        target=language(self.config.target).name
        message=getattr(self,"last_status","Loading models...")
        source=LANGUAGES[self.detected_source].name if self.detected_source in LANGUAGES else self.detected_source
        floating.set_status(source,target,message,self.ready,self.busy,self.auto)
        if hasattr(self,"floating_header"):
            self.floating_header.setText("HALO TEXT | English > "+target)
            self.floating_status.setText(message[:72])

    def set_floating_visible(self,visible):
        if self.floating is None:
            return
        visible=bool(visible) and not self.exiting
        if visible:
            self.floating.ensure_on_screen()
            if self.floating.apply_exclusion():
                self.floating.show()
                self.floating.raise_()
            else:
                visible=False
        else:
            self.floating.hide()
        self.floating_action.setChecked(visible and self.floating.isVisible())

    def floating_unavailable(self):
        self.floating.hide()
        self.floating_action.setChecked(False)
        log.warning("Floating icon capture exclusion unavailable")
        self.status("Floating icon unavailable in this session. Use the H tray menu.",notify=True)

    def open_floating_controls(self,position):
        if not self.exiting:
            self.update_floating()
            self.floating_menu.popup(position)

    def begin_controls(self):
        if self.controls_depth==0:
            self.resume_after_controls=bool(self.overlay.items or self.busy or self.wanted)
            self.invalidate()
        self.controls_depth+=1

    def end_controls(self):
        self.controls_depth=max(0,self.controls_depth-1)
        if self.controls_depth==0:
            self.signature=None
            self.changed_at=monotonic()
            if (self.resume_after_controls and self.region is not None and self.ready
                    and self.selector is None and not self.exiting):
                self.wanted=True
            self.resume_after_controls=False

    def show_help(self):
        self.begin_controls()
        try:
            box=QMessageBox(self.floating if self.floating and self.floating.isVisible() else None)
            box.setWindowTitle("HALO TEXT controls")
            box.setIcon(QMessageBox.Icon.Information)
            box.setText("HALO TEXT | Input: "+self.config.input_language+" > "+language(self.config.target).name)
            box.setInformativeText(
                "Drag the floating H to move it. Right-click it for controls.\n"
                "Double-click H or press Ctrl+Alt+R to select an area.\n\n"
                "Ctrl+Alt+R  Select area and start watching\n"
                "Ctrl+Alt+T  Translate current area\n"
                "Ctrl+Alt+F  Translate screen under pointer\n"
                "Ctrl+Alt+A  Pause/resume watching\n"
                "Ctrl+Alt+O  Show original/translated text\n"
                "Ctrl+Alt+C  Clear translations and selection box\n"
                "Ctrl+Alt+Q  Exit HALO TEXT\n"
                "Esc  Cancel an unfinished selection\n\n"
                "Green border: watching. Amber: paused. Scroll normally; new stable text translates.\n"
                "Change output in Translation language > Indian / Global languages.\n"
                "Downloaded language models lists installed packs. All 22 Indian outputs share one pack.\n"
                "Faster captions samples moving video continuously. Select only the subtitle strip.\n"
                "Keep last caption holds the previous translation until a replacement is ready.\n"
                "Follow selected window moves and resizes the box with that window on the same display.\n"
                "Check speed measures OCR for the selected area, excluding online translation.\n"
                "Online labels mean recognized text is sent to Google.\n\n"
                "Input OCR packs extend supported scripts; Google can check ambiguous recognized text, not unreadable pixels.\n"
                "Audio: choose System audio or Microphone, then output mode and subtitle delay. Voice labels are approximate pitch groups, not speaker identity. Hindi speech can run offline after its voice pack is downloaded; other supported voices use Microsoft online. Feedback prevention pauses capture during playback.")
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.exec()
        finally:
            self.end_controls()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.dispatch("region")

    def models_ready(self):
        self.initializing = False
        self.ready = True
        if self.exiting:
            self.thread.quit()
            return
        message = "Ready. Ctrl+Alt+R selects text; Ctrl+Alt+T translates."
        if self.hotkeys.failures:
            message += " Some shortcuts are in use; use the H tray menu."
        self.status(message, notify=True)

    def set_fast_captions(self,enabled):
        self.config=replace(self.config,fast_captions=bool(enabled))
        self.timer.setInterval(self.config.watch_timing()[0])
        self.invalidate()
        if self.region is not None and self.ready:
            self.wanted=True
        self.status("Faster captions on. Continuously sampling the subtitle strip; translation can lag the video."
                    if enabled else "Document timing restored.")

    def set_visual_option(self,name,enabled):
        self.config=replace(self.config,**{name:bool(enabled)})
        if name=="caption_hold":self.caption_hold_action.setChecked(enabled)
        if name=="follow_window":
            self.follow_action.setChecked(enabled)
            self.follow_binding=self.make_follow_binding() if enabled else None

    def check_performance(self):
        if not self.ready:return
        try:frame=self.capture.grab(self.region) if self.region is not None else None
        except Exception:frame=None
        self.status("Measuring OCR speed on this computer...")
        self.request_benchmark.emit(frame)

    def show_performance(self,result):
        if self.exiting:return
        if "error" in result:
            self.status("Speed check could not finish: "+result["error"],notify=True)
            return
        ms=result["ocr_ms"]
        translation_ms=result.get("translation_ms")
        size=result["image"]
        gpu=("DirectML is installed, but HALO currently uses CPU OCR."
             if result["directml_available"] else
             "DirectML GPU acceleration is not installed in this HALO runtime.")
        advice=("OCR is relatively slow here. Select only the caption strip, keep fewer OCR packs installed, and prefer offline translation."
                if ms>300 else "OCR speed looks suitable for a narrow caption strip. Online translation may still add network delay.")
        box=QMessageBox(self.floating if self.floating and self.floating.isVisible() else None)
        box.setWindowTitle("HALO speed check")
        box.setText(f"Median OCR time: {ms} ms for {size[0]} × {size[1]} pixels")
        translation=(f"Local translation: {translation_ms} ms for one sample sentence."
                     if translation_ms is not None else "Online translation timing varies by connection and was not measured.")
        box.setInformativeText(f"{translation}\n{advice}\n\n{gpu}\nCPU threads: {result['threads']}. Capture and display are not included.")
        box.exec()

    def set_auto(self, enabled):
        self.auto = enabled
        self.outline.set_watching(enabled)
        self.auto_action.blockSignals(True)
        self.auto_action.setChecked(enabled)
        self.auto_action.blockSignals(False)
        self.update_floating()

    def clear_visuals(self):
        self.caption_expires_at = 0.0
        self.displayed_frame = None
        self.displayed_boxes = []
        self.overlay.clear()

    def control(self, command):
        snapshot = {"running": True, "pid": os.getpid(), "ready": self.ready,
                    "initializing": self.initializing, "busy": self.busy,
                    "selection_border": self.outline.isVisible(),
                    "automatic": self.auto, "displayed_blocks": len(self.overlay.items),
                    "fast_captions": self.config.fast_captions,
                    "watch_timing_ms": self.config.watch_timing(),
                    "backend": self.config.backend, "active_provider": route(self.config), "source": self.detected_source,
                    "input_mode":self.config.input_language,"target": self.config.target,
                    "original_visible": self.overlay.original_visible,
                    "audio": {"enabled":self.audio_enabled,"status":self.audio_status,
                              "source":self.audio_session.source if self.audio_session else None,
                              "spoken":self.config.audio_spoken,"voice_running":self.voice_session is not None,
                              "voice_status":self.voice_status_action.text(),"feedback_guard":self.config.audio_feedback_guard},
                    "display": self.screen.name() if self.screen in self.application.screens() else None,
                    "available_displays": [screen.name() for screen in self.application.screens()],
                    "message": getattr(self, "last_status", "Starting..."),
                    "floating_icon": {"visible": self.floating.isVisible(),
                                      "x": self.floating.x(),"y": self.floating.y(),
                                      "capture_excluded": self.floating.excluded},
                    "controls_open": self.controls_depth>0,
                    "hotkey_conflicts": self.hotkeys.failures}
        if command == "stop":
            QTimer.singleShot(100, self.quit)
            snapshot["message"] = "Graceful shutdown requested."
        elif command == "clear":
            self.clear()
            snapshot.update(automatic=False, displayed_blocks=0, original_visible=False, message="Paused.")
        elif command == "audio-stop":
            self.stop_audio()
            snapshot["audio"]["enabled"] = False
            snapshot["audio"]["status"] = self.audio_status
        elif command == "original":
            self.dispatch("original")
            snapshot["original_visible"] = self.overlay.original_visible
        elif command == "activate":
            self.status(snapshot["message"], notify=True)
        return snapshot

    def invalidate(self):
        self.generation += 1
        self.signature = None
        self.caption_frame = None
        self.changed_at = monotonic()
        self.clear_visuals()

    def clear(self):
        self.set_auto(False)
        self.wanted = False
        self.invalidate()
        self.set_original(False)
        self.outline.clear()
        self.follow_binding=None
        self.status("Paused. Ctrl+Alt+T to translate again.")

    def dispatch(self, name):
        if self.exiting:
            return
        if name == "quit":
            self.quit()
            return
        if name == "clear":
            if self.selector:
                self.selector.cancel()
            self.clear()
            return
        if name == "audio":
            if self.audio_session:
                self.stop_audio()
            else:
                self.toggle_audio(self.config.audio_source)
            return
        if name == "original":
            if self.overlay.original_visible:
                self.tick()  # Recheck source content before revealing a cached overlay.
            self.set_original(not self.overlay.original_visible)
            self.status("Original text visible. Ctrl+Alt+O restores translations."
                        if self.overlay.original_visible else "Translation overlay visible.")
            return
        if self.display_pending:
            self.status("Display is changing. Try again in a moment.")
            return
        if not self.ready:
            self.status(self.load_error or "Models are loading. Please wait.", notify=True)
            return
        if name in ("region","screen","translate") and route(self.config)=="missing":
            self.status("Download the selected language model before translating.",notify=True)
            return
        if name == "region":
            self.choose_region()
        elif name == "screen":
            self.clear()
            if self.selector:
                self.selector.cancel()
            if not self.switch_screen(self.pointer_screen()):
                return
            self.use_full_screen()
            self.wanted = True
            self.status("Waiting for the screen to settle...")
        elif name == "translate":
            if self.selector:
                return
            if self.region is None:
                self.use_full_screen()
            self.clear_visuals()
            self.show_outline()
            self.wanted = True
            self.completed_generation = -1
            self.status("Waiting for stable text...")
            self.tick()
        elif name == "auto":
            if self.selector:
                return
            self.set_auto(not self.auto)
            if self.region is None:
                self.use_full_screen()
            self.wanted = self.auto
            if not self.auto:
                self.invalidate()
            self.show_outline()
            self.status("Watching selected area. Scroll to translate new text." if self.auto else "Watching paused. Ctrl+Alt+A resumes.")

    def show_outline(self):
        if self.region is not None:
            self.outline.set_region(self.capture.mapping,self.region,self.auto)

    def set_original(self, visible):
        self.overlay.set_original_visible(visible)
        self.original_action.blockSignals(True)
        self.original_action.setChecked(visible)
        self.original_action.blockSignals(False)

    def pointer_screen(self):
        return self.application.screenAt(QCursor.pos()) or self.application.primaryScreen()

    def populate_monitors(self):
        self.monitor_menu.clear()
        for screen in self.application.screens():
            geometry = screen.geometry()
            action = self.monitor_menu.addAction(f"{screen.name()} ({geometry.width()} x {geometry.height()})")
            action.setCheckable(True)
            action.setChecked(screen is self.screen)
            action.triggered.connect(lambda checked=False, selected=screen: self.choose_region(selected))

    def download_model(self):
        if self.model_download or self.exiting or not self.ready:return
        if self.config.target == "en":
            self.status("English output needs no English-to-English translation model.",notify=True)
            return
        self.download_kind="translation"
        self.resume_after_language=self.auto
        self.set_auto(False);self.invalidate();self.show_outline();self.stop_audio()
        self.download_target=self.config.target
        self.download_action.setEnabled(False)
        size_note=" The shared Indian-language pack is about 850 MB and resumes after interruptions." if language(self.download_target).group=="Indian" else ""
        self.status("Preparing offline "+language(self.download_target).name+" model."+size_note,notify=True)
        self.start_model_download("--install-model",self.download_target)

    def start_model_download(self,*arguments):
        self.last_download_line=""
        log_path=STATE/"model-download.log"
        self.model_log_offset=log_path.stat().st_size if log_path.exists() else 0
        self.model_download=QProcess(self)
        self.model_download.setWorkingDirectory(str(ROOT))
        self.model_download.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.model_download.readyReadStandardOutput.connect(self.model_download_output)
        self.model_download.finished.connect(self.model_download_finished)
        self.model_download.errorOccurred.connect(self.model_download_error)
        if getattr(sys,"frozen",False):
            self.model_log_timer.start()
        self.model_download.start(*model_command(*arguments))

    def show_model_download_output(self,text):
        lines=[line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            self.last_download_line=lines[-1]
            self.status("Offline model: "+self.last_download_line[:180])

    def poll_model_download_log(self):
        path=STATE/"model-download.log"
        try:
            with path.open("rb") as stream:
                stream.seek(self.model_log_offset)
                data=stream.read()
                self.model_log_offset=stream.tell()
        except FileNotFoundError:
            return
        if data:
            self.show_model_download_output(data.decode("utf-8",errors="replace"))

    def model_download_output(self):
        if self.model_download is None:return
        text=bytes(self.model_download.readAllStandardOutput()).decode("utf-8",errors="replace")
        with (STATE/"model-download.log").open("a",encoding="utf-8") as log_file:log_file.write(text)
        self.show_model_download_output(text)

    def model_download_error(self,error):
        if error==QProcess.ProcessError.FailedToStart:self.model_download_finished(-1)

    def model_download_finished(self,code,*args):
        if getattr(sys,"frozen",False):
            self.poll_model_download_log()
            self.model_log_timer.stop()
        process,self.model_download=self.model_download,None
        kind=getattr(self,"download_kind","translation")
        if process:process.deleteLater()
        self.download_action.setEnabled(True)
        if self.exiting:return
        if code!=0:
            detail=(" "+self.last_download_line[:170]) if self.last_download_line else " See runtime/state/model-download.log."
            if kind in {"ocr","pair"}:
                self.status("Input or translation pack download failed."+detail,notify=True)
                return
            if kind!="translation":
                self.status("Audio model download failed."+detail,notify=True)
                return
            if self.resume_after_language and self.region is not None:
                self.set_auto(True)
                self.wanted=True
            self.resume_after_language=False
            self.status("Offline pack unavailable or download failed."+detail,notify=True)
            return
        if kind in {"ocr","pair"}:
            if kind=="pair":
                self.request_source_route.emit(self.download_source,self.download_pair_target,"local")
            self.ready=False;self.initializing=True
            self.status("Loading new language pack...")
            if self.region is not None:
                self.wanted=True
            self.request_language.emit(self.config)
            return
        if kind!="translation":
            self.status(("Hindi voice pack" if kind=="voices-hi" else "English speech model")+" installed. Start audio to use it.",notify=True)
            return
        if self.config.target==self.download_target:
            self.ready=False;self.initializing=True
            self.status("Warming installed "+language(self.config.target).name+" model...")
            self.request_language.emit(self.config)
        else:self.status("Offline "+language(self.download_target).name+" pack installed. Select it in Translation language.",notify=True)

    def populate_downloaded_models(self):
        from .model_manager import installed_models
        self.models_menu.clear()
        models=installed_models()
        translation=[entry for entry in models if entry.kind=="translation"]
        audio=[entry for entry in models if entry.kind=="audio"]
        label=self.models_menu.addAction("Translation models (only the selected one loads)")
        label.setEnabled(False)
        if not translation:
            empty=self.models_menu.addAction("No downloaded translation models")
            empty.setEnabled(False)
        for entry in translation:
            size=f"{entry.size_bytes/1048576:.0f} MB"
            current=self.config.target in entry.languages
            suffix=" — in use" if current else " — remove"
            action=self.models_menu.addAction(entry.title+f" ({size})"+suffix)
            action.setEnabled(not current and self.model_download is None and self.ready)
            if not current:
                action.triggered.connect(lambda checked=False,key=entry.key:self.remove_downloaded_model(key))
        self.models_menu.addSeparator()
        label=self.models_menu.addAction("Audio models")
        label.setEnabled(False)
        for entry in audio:
            size=f"{entry.size_bytes/1048576:.0f} MB"
            action=self.models_menu.addAction(entry.title+f" ({size}) — remove")
            action.setEnabled(not self.audio_enabled and self.voice_session is None and self.model_download is None)
            action.triggered.connect(lambda checked=False,key=entry.key:self.remove_downloaded_model(key))
        self.models_menu.addSeparator()
        label=self.models_menu.addAction("Input OCR packs")
        label.setEnabled(False)
        for entry in models:
            if entry.kind!="ocr":continue
            action=self.models_menu.addAction(entry.title+f" ({entry.size_bytes/1048576:.0f} MB) — remove")
            action.setEnabled(not self.busy and self.model_download is None)
            action.triggered.connect(lambda checked=False,key=entry.key:self.remove_downloaded_model(key))
        if not any(entry.key=="speech" for entry in audio):
            action=self.models_menu.addAction("Download English speech recognition")
            action.setEnabled(not self.audio_enabled and self.model_download is None)
            action.triggered.connect(lambda:self.download_audio_model("speech"))
        if not any(entry.key=="voices-hi" for entry in audio):
            action=self.models_menu.addAction("Download Hindi spoken voices")
            action.setEnabled(not self.audio_enabled and self.model_download is None)
            action.triggered.connect(lambda:self.download_audio_model("voices-hi"))
        self.models_menu.addSeparator()
        note=self.models_menu.addAction("All 22 Indian outputs use the shared Indian-language pack")
        note.setEnabled(False)

    def remove_downloaded_model(self,key):
        if self.exiting or self.model_download or not self.ready:return
        from .model_manager import installed_models,remove_model
        entry=next((item for item in installed_models() if item.key==key),None)
        if entry is None:
            self.status("Model list changed. Open Downloaded language models again.",notify=True)
            return
        if entry.kind=="translation" and self.config.target in entry.languages:
            self.status("Select another output language before removing its model.",notify=True)
            return
        if entry.kind=="audio" and (self.audio_enabled or self.voice_session is not None):
            self.status("Stop audio translation before removing an audio model.",notify=True)
            return
        answer=QMessageBox.question(self.floating if self.floating and self.floating.isVisible() else None,
                                    "Remove downloaded model",
                                    f"Remove {entry.title} ({entry.size_bytes/1048576:.0f} MB)?\nYou can download it again later.",
                                    QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        if entry.kind=="ocr":
            self.request_drop_ocr.emit(key.split(":",1)[1])
            return
        try:
            removed=remove_model(key,self.config.target,self.audio_enabled or self.voice_session is not None)
            self.status(removed.title+" removed. Freed about "+f"{removed.size_bytes/1048576:.0f} MB.",notify=True)
        except (OSError,RuntimeError) as exc:
            self.status("Could not remove model: "+str(exc)[:140],notify=True)

    def ocr_dropped(self,pack):
        from .model_manager import remove_model
        try:
            removed=remove_model("ocr:"+pack,self.config.target,self.audio_enabled)
            self.status(removed.title+" removed. You can download it again.",notify=True)
        except (OSError,RuntimeError) as exc:
            self.status("Could not remove OCR pack: "+str(exc)[:140],notify=True)

    def download_audio_model(self,kind):
        if self.model_download or self.audio_enabled or self.exiting:return
        if kind not in {"speech","voices-hi"}:return
        self.download_kind=kind
        self.download_action.setEnabled(False)
        self.status("Downloading "+("Hindi spoken voices" if kind=="voices-hi" else "English speech recognition")+"...",notify=True)
        option="--install-voices" if kind=="voices-hi" else "--install-audio"
        self.start_model_download(option)

    def populate_languages(self):
        self.language_menu.clear()
        self.language_menu.addSection("Offline labels stay local; online labels send recognized text to Google")
        for group in ("Indian","Global"):
            menu=self.language_menu.addMenu(group+" languages")
            for code,item in LANGUAGES.items():
                if item.group!=group:
                    continue
                selected=route(replace(self.config,target=code))
                label={"local":"offline","indic":"offline pack","web":"online","groq":"Groq","missing":"pack needed"}[selected]
                action=menu.addAction(item.name+" ("+label+")")
                action.setCheckable(True)
                action.setChecked(code==self.config.target)
                action.setEnabled(self.ready)
                action.triggered.connect(lambda checked=False,target=code:self.change_language(target))

    def populate_ocr_packs(self):
        from .ocr_packs import PACKS,LANGUAGE_PACK,installed
        self.ocr_menu.clear()
        notice=self.ocr_menu.addAction("English OCR is built in; add packs for other scripts")
        notice.setEnabled(False)
        for key,(title,*_) in PACKS.items():
            present=installed(key)
            action=self.ocr_menu.addAction(title+(" — installed" if present else " — download"))
            action.setEnabled(not present and self.model_download is None and self.ready)
            if not present:
                action.triggered.connect(lambda checked=False,pack=key:self.download_ocr_pack(pack))
        self.ocr_menu.addSeparator()
        catalog=self.ocr_menu.addMenu("Browse by input language")
        for group in ("Indian","Global"):
            section=catalog.addMenu(group+" languages")
            for code,item in LANGUAGES.items():
                if item.group!=group:continue
                if code=="en":
                    action=section.addAction("English — built in")
                    action.setEnabled(False)
                    continue
                pack=LANGUAGE_PACK.get(code)
                if pack is None:
                    action=section.addAction(item.name+" — OCR pack unavailable")
                    action.setEnabled(False)
                    continue
                present=installed(pack)
                action=section.addAction(item.name+" — "+pack+(" installed" if present else " download"))
                action.setEnabled(not present and self.model_download is None and self.ready)
                if not present:
                    action.triggered.connect(lambda checked=False,key=pack:self.download_ocr_pack(key))

    def populate_input_languages(self):
        from .ocr_packs import LANGUAGE_PACK,installed
        self.input_menu.clear()
        automatic=self.input_menu.addAction("Automatic detection")
        automatic.setCheckable(True)
        automatic.setChecked(self.config.input_language=="auto")
        automatic.triggered.connect(lambda:self.change_input_language("auto"))
        english=self.input_menu.addAction("English (built-in OCR)")
        english.setCheckable(True)
        english.setChecked(self.config.input_language=="en")
        english.triggered.connect(lambda:self.change_input_language("en"))
        for group in ("Indian","Global"):
            section=self.input_menu.addMenu(group+" input languages")
            for code,item in LANGUAGES.items():
                if item.group!=group or code=="en":continue
                pack=LANGUAGE_PACK.get(code)
                ready=bool(pack and installed(pack))
                suffix="" if ready else " — OCR pack needed" if pack else " — OCR unavailable"
                action=section.addAction(item.name+suffix)
                action.setCheckable(True)
                action.setChecked(self.config.input_language==code)
                action.setEnabled(ready and self.ready)
                if ready:
                    action.triggered.connect(lambda checked=False,source=code:self.change_input_language(source))

    def change_input_language(self,source):
        if not self.ready or self.exiting or source==self.config.input_language:return
        if self.selector:self.selector.cancel()
        self.resume_after_language=self.auto
        self.clear()
        self.show_outline()
        self.stop_audio()
        self.detected_source="en" if source=="auto" else source
        self.ready=False;self.initializing=True
        self.status("Loading input OCR route...")
        self.request_language.emit(replace(self.config,input_language=source))

    def download_ocr_pack(self,key):
        from .ocr_packs import PACKS
        if key not in PACKS or self.model_download or not self.ready:return
        self.download_kind="ocr"
        self.status("Downloading "+PACKS[key][0]+" OCR pack...",notify=True)
        self.start_model_download("--install-ocr",key)

    def download_source_pair(self,source):
        if self.model_download or not self.ready:return
        self.download_kind="pair"
        self.download_source=source
        self.download_pair_target=self.config.target
        self.status(f"Downloading offline {source} → {self.config.target} translation pack...",notify=True)
        self.start_model_download("--install-pair",source,self.download_pair_target)

    def change_language(self, target):
        language(target)
        if not self.ready or target == self.config.target or self.exiting:
            return
        if route(replace(self.config,target=target)) == "missing":
            if self.selector:
                self.selector.cancel()
            self.clear()
            self.config=replace(self.config,target=target)
            self.overlay.config=self.config
            self.status(f"{language(target).name} needs its offline pack. Choose Download offline model for selected language.",notify=True)
            return
        if self.selector:
            self.selector.cancel()
        self.resume_after_language = self.auto
        self.clear()
        self.show_outline()
        self.stop_audio()
        self.ready = False
        self.initializing = True
        self.status(f"Loading {language(target).name}...")
        self.request_language.emit(replace(self.config,target=target))

    def language_ready(self, config):
        self.config = config
        self.overlay.config = config
        self.initializing = False
        self.ready = True
        if self.exiting:
            self.thread.quit()
            return
        if self.resume_after_language and self.region is not None:
            self.set_auto(True)
            self.wanted = True
        self.resume_after_language = False
        self.show_outline()
        self.status(f"{language(config.target).name} ready. Watching area." if self.auto else
                    f"{language(config.target).name} ready. Ctrl+Alt+T translates.",notify=True)

    def language_failed(self, message):
        self.resume_after_language = False
        self.initializing = False
        self.ready = True
        if self.exiting:
            self.thread.quit()
            return
        self.status(message,notify=True)

    def switch_screen(self, screen, force=False):
        if screen is None:
            self.status("No display is available.",notify=True)
            return False
        if screen is self.screen and not force:
            return True
        replacement = None
        overlay = None
        outline = None
        try:
            replacement = ScreenCapture(screen)
            overlay = Overlay(screen,self.config)
            outline = SelectionOutline(screen)
            if not overlay.excluded or not outline.excluded:
                raise RuntimeError("Capture exclusion failed on this display.")
        except Exception:
            if replacement:
                replacement.close()
            if overlay:
                overlay.close()
                overlay.deleteLater()
            if outline:
                outline.close()
                outline.deleteLater()
            log.exception("Could not select display")
            self.status("Could not use this display. Select another display and retry.",notify=True)
            return False
        self.stop_audio()
        self.clear()
        self.region = None
        try:
            self.screen.geometryChanged.disconnect(self.display_changed)
            self.screen.logicalDotsPerInchChanged.disconnect(self.display_changed)
        except (RuntimeError,TypeError):
            pass
        self.capture.close()
        self.overlay.close()
        self.overlay.deleteLater()
        self.outline.close()
        self.outline.deleteLater()
        self.capture,self.overlay,self.outline,self.screen = replacement,overlay,outline,screen
        self.bind_screen_signals()
        return True

    def use_full_screen(self):
        m = self.capture.mapping
        self.region = Box(0,0,m.width,m.height)
        self.follow_binding=None
        self.invalidate()
        self.show_outline()

    def choose_region(self, screen=None):
        if not self.ready or self.display_pending:
            return
        self.clear()
        if self.selector:
            self.selector.cancel()
        if not self.switch_screen(screen or self.pointer_screen()):
            return
        if self.selector:
            self.selector.close()
        self.selector = RegionSelector(self.screen)
        self.selector.selected.connect(self.region_selected)
        self.selector.cancelled.connect(self.region_cancelled)
        self.selector.show()
        self.selector.activateWindow()
        self.selector.raise_()

    def region_cancelled(self):
        selector, self.selector = self.selector, None
        if selector:
            selector.deleteLater()
        self.status("Selection cancelled. Ctrl+Alt+R to try again.")

    def region_selected(self, rect):
        self.region = self.capture.mapping.to_physical((rect.x(),rect.y(),rect.width(),rect.height()))
        selector, self.selector = self.selector, None
        if selector:
            selector.deleteLater()
        self.follow_binding=self.make_follow_binding() if self.config.follow_window else None
        self.invalidate()
        self.set_auto(self.config.auto_on_select)
        self.show_outline()
        self.wanted = True
        self.status("Area selected. Watching for text after scrolling." if self.auto
                    else "Area selected. Translating when the text settles...")

    def make_follow_binding(self):
        if self.region is None:return None
        from .windows import window_at,window_rect
        m=self.capture.mapping
        absolute=(m.left+self.region.x,m.top+self.region.y,self.region.w,self.region.h)
        hwnd=window_at(*absolute)
        rect=window_rect(hwnd) if hwnd else None
        if not rect:return None
        x,y,w,h=rect
        return hwnd,((absolute[0]-x)/w,(absolute[1]-y)/h,absolute[2]/w,absolute[3]/h)

    def update_followed_region(self):
        if not self.config.follow_window or not self.follow_binding or self.region is None:return
        from .windows import window_rect
        hwnd,relative=self.follow_binding
        rect=window_rect(hwnd)
        if rect is None:return
        x,y,w,h=rect
        rx,ry,rw,rh=relative
        m=self.capture.mapping
        moved=Box(round(x+rx*w-m.left),round(y+ry*h-m.top),round(rw*w),round(rh*h))
        if moved!=moved.clip(m.width,m.height) or moved.w<60 or moved.h<30:
            return  # Keep the old selection until the window returns to this display.
        if moved!=self.region:
            self.region=moved
            self.invalidate()
            self.show_outline()
            self.wanted=True

    def tick(self):
        self.update_followed_region()
        if monotonic() < getattr(self, "online_retry_after", 0.0):
            return
        if (self.exiting or self.controls_depth or not self.ready or self.selector or self.region is None
                or not (self.auto or self.wanted or self.busy or self.overlay.items)):
            return
        if self.display_pending or not desktop_available():
            self.invalidate()
            return
        if self.config.fast_captions:
            now = monotonic()
            if (not self.config.caption_hold and self.caption_expires_at
                    and now >= self.caption_expires_at and not self.auto):
                self.clear_visuals()
            due = (now-self.last_submit)*1000 >= self.config.watch_timing()[2]
            # Do not capture unused frames while the only worker is busy.
            if self.busy or not (self.wanted or (self.auto and due)):
                return
        try:
            frame = self.capture.grab(self.region)
            signature = None if self.config.fast_captions else frame_signature(frame)
        except Exception as exc:
            self.clear()
            self.status("Screen capture unavailable. Select the area again.", notify=True)
            log.warning("Capture unavailable: %s", type(exc).__name__)
            return
        now = monotonic()
        if self.config.fast_captions:
            # Movie pixels never settle. Sample the latest frame instead of resetting
            # document generations on every background change. Only one job is in flight.
            # An identical subtitle strip cannot contain a new caption. Keep its
            # translation visible and spare the CPU a duplicate OCR pass.
            if (not self.wanted and getattr(self,"caption_frame",None) is not None
                    and np.array_equal(frame,self.caption_frame)):
                if self.overlay.items:
                    self.caption_expires_at=now+2.0
                return
            if not self.config.caption_hold and self.caption_expires_at and now >= self.caption_expires_at:
                self.clear_visuals()
            due = (now-self.last_submit)*1000 >= self.config.watch_timing()[2]
            if not self.busy and (self.wanted or (self.auto and due)):
                self.busy = True
                self.wanted = False
                self.last_submit = now
                self.job_frame = frame
                self.caption_frame = frame
                self.status("Reading latest video caption...")
                self.request_job.emit(self.generation,frame,True)
            return
        if (frames_differ(self.signature, signature) or
                text_regions_differ(self.displayed_frame, frame, self.displayed_boxes)):
            self.generation += 1
            self.signature = signature
            self.changed_at = now
            self.clear_visuals()
        _,settle_ms,auto_interval_ms = self.config.watch_timing()
        stable = (now-self.changed_at)*1000 >= settle_ms
        due = (now-self.last_submit)*1000 >= auto_interval_ms
        needed = self.wanted or (self.auto and self.completed_generation != self.generation and due)
        if stable and needed and not self.busy:
            self.busy = True
            self.wanted = False
            self.last_submit = now
            self.status("Recognizing and translating...")
            self.job_frame = frame
            self.request_job.emit(self.generation, frame, self.config.fast_captions)

    def finished(self, generation, result):
        self.busy = False
        self.online_retry_after = 0.0
        if self.exiting:
            self.thread.quit()
            return
        # Capture again before painting: a completed result is not necessarily current.
        valid = (generation == self.generation and self.selector is None
                 and not getattr(self,"controls_depth",0) and desktop_available())
        streaming = bool(getattr(getattr(self,"config",None),"fast_captions",False))
        if valid and streaming and monotonic()-self.last_submit > 2.0:
            # A slow result is still current on a static page or paused video.
            # Discard it only if its source frame actually changed.
            try:
                unchanged = self.job_frame is not None and np.array_equal(
                    self.job_frame, self.capture.grab(self.region))
            except Exception:
                unchanged = False
            if not unchanged:
                self.job_frame = None
                if not self.config.caption_hold:self.clear_visuals()
                self.status("Caption changed while processing. Reading the latest frame; a smaller area or offline target is faster.")
                return
        if valid and not streaming:
            try:
                current_frame = self.capture.grab(self.region)
                current = frame_signature(current_frame)
                boxes = [item.block.box for item in result.translations]
                valid = (not frames_differ(self.signature, current)
                         and not text_regions_differ(self.job_frame, current_frame, boxes))
            except Exception:
                valid = False
        if not valid:
            self.job_frame = None
            if not self.ready:
                return
            self.status("Content changed. Press Ctrl+Alt+T again." if not self.auto
                        else "Content changed. Waiting for stable text...")
            return
        if streaming and self.config.caption_hold and not result.translations:
            displayed,skipped=len(self.overlay.items),0
        else:
            displayed, skipped = self.overlay.show_translations(result.translations, self.capture.mapping, self.region)
        self.detected_source=getattr(result,"source","en")
        self.displayed_frame = self.job_frame if displayed else None
        self.displayed_boxes = [item.block.box for item in result.translations] if displayed else []
        self.job_frame = None
        self.completed_generation = generation
        if streaming:
            # Bound how long sampled text can survive, measured from its source frame.
            self.caption_expires_at = self.last_submit+2.0 if displayed else 0.0
        mode = "Captions" if streaming else "Auto" if self.auto else "Manual"
        message = f"{mode}: {displayed} blocks | {result.metrics['total_ms']/1000:.1f}s"
        if skipped:
            message += f" | {skipped} too small to fit"
        if not result.translations:
            message = "No readable text found. Add an input OCR pack for non-English text."
            if streaming and self.config.caption_hold and displayed:
                message = "No new caption read. Keeping the previous translation."
        elif getattr(result,"source","en") != "en":
            source=result.source
            message += f" | input: {LANGUAGES[source].name if source in LANGUAGES else source}"
        self.status(message)
        metrics = dict(result.metrics, displayed=displayed, skipped=skipped, backend=self.config.backend)
        # Timing only: no screenshots, recognized text, translations, or API keys.
        log.info("metrics %s", json.dumps(metrics))

    def failed(self, generation, message):
        self.busy = False
        self.job_frame = None
        if generation == -1:
            self.initializing = False
            self.load_error = "Startup failed. Check runtime/state/halo.log, run setup, then restart."
        if self.exiting:
            self.thread.quit()
            return
        if generation >= 0 and generation != self.generation:
            return
        if message.startswith("Online translation limit reached") and self.auto:
            self.online_retry_after = monotonic() + 30.0
            self.status("Online translation is rate-limited. Watching remains on; retrying automatically in 30 seconds.", notify=True)
            return
        if message.startswith("OCR_PACK_CHOICE:"):
            _,source,pack=message.split(":",2)
            from .ocr_packs import PACKS
            title=LANGUAGES[source].name if source in LANGUAGES else source
            box=QMessageBox(self.floating if self.floating and self.floating.isVisible() else None)
            box.setWindowTitle("Download input language pack")
            box.setText(f"HALO identified {title} text. Download its {PACKS[pack][0]} OCR pack to continue?")
            box.setInformativeText("Only recognized text was sent to Google for language identification. The OCR pack is stored on this computer and can be removed in Downloaded language models.")
            download=box.addButton("Download OCR pack",QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Later",QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is download:
                self.download_ocr_pack(pack)
            else:
                self.status(f"{title} translation paused. Download its input OCR pack to continue.",notify=True)
            return
        if message.startswith("SOURCE_CHOICE:"):
            _,source,availability=message.split(":",2)
            title=LANGUAGES[source].name if source in LANGUAGES else source
            box=QMessageBox(self.floating if self.floating and self.floating.isVisible() else None)
            box.setWindowTitle("Choose translation route")
            box.setText(f"HALO detected {title} input. How should it translate to {language(self.config.target).name}?")
            box.setInformativeText("Online sends recognized text, not screenshots. An offline pack is downloaded only if a direct model exists.")
            online=box.addButton("Use online",QMessageBox.ButtonRole.AcceptRole)
            offline=box.addButton("Use installed offline pack" if availability=="installed" else "Download offline pack",
                                  QMessageBox.ButtonRole.ActionRole)
            box.addButton("Cancel",QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is online:
                self.request_source_route.emit(source,self.config.target,"web")
                self.wanted=True
                self.changed_at=monotonic()
                self.status(f"Online {title} translation selected. Retrying...",notify=True)
            elif box.clickedButton() is offline:
                if availability=="installed":
                    self.request_source_route.emit(source,self.config.target,"local")
                    self.wanted=True
                    self.changed_at=monotonic()
                    self.status(f"Offline {title} translation selected. Retrying...",notify=True)
                else:
                    self.download_source_pair(source)
            else:
                self.status(f"{title} translation paused. Select an online or offline route to continue.",notify=True)
            return
        if self.config.fast_captions and self.config.caption_hold and self.overlay.items:
            self.status("Caption update failed; keeping the previous translation. "+message[:180],notify=True)
            return
        self.clear()
        self.show_outline()
        self.status(message[:240], notify=True)

    def toggle_audio(self, source):
        if self.exiting:
            return
        if self.audio_session:
            self.stop_audio()
            return
        if not self.ready or self.display_pending:
            self.status("Wait until models and display are ready before starting audio.",notify=True)
            return
        if route(self.config)=="missing":
            self.status("Download the selected language model before starting audio translation.",notify=True)
            return
        from .speech_setup import installed
        if not installed():
            self.status("Install speech support first: app/run.py --install-audio",notify=True)
            return
        from .audio import AudioSession
        if self.config.audio_show_subtitles and not self.open_audio_overlay():return
        self.audio_enabled = True
        from .audio_core import ApproximateVoiceLabels
        self.voice_labels=ApproximateVoiceLabels()
        self.audio_display_token+=1
        self.echo_gate.clear()
        self.voice_ready.clear()
        if not self.config.audio_spoken:self.voice_ready.set()
        self.audio_session = AudioSession(self.config,source,parent=self,echo_gate=self.echo_gate,output_ready=self.voice_ready)
        self.audio_session.state.connect(self.audio_state_changed)
        self.audio_session.subtitle.connect(self.audio_subtitle)
        self.audio_session.failed.connect(self.audio_failed)
        self.audio_session.finished.connect(self.audio_stopped)
        for name,action in self.audio_actions.items():
            action.setChecked(name == source)
        self.audio_state_changed("Loading speech model...")
        self.audio_session.start()
        self.start_voice()
        self.tray.showMessage("HALO TEXT audio",
                              "Starting "+source+" translation. Ctrl+Alt+S stops listening and speech.",
                              QSystemTrayIcon.MessageIcon.Information,4000)

    def open_audio_overlay(self):
        from .subtitles import SubtitleOverlay
        overlay=SubtitleOverlay(self.screen,self.config.target)
        if not overlay.excluded:
            overlay.close();overlay.deleteLater()
            self.status("Audio overlay could not be excluded from capture.",notify=True)
            return False
        self.audio_overlay=overlay
        return True

    def sync_audio_controls(self):
        for mode,action in self.audio_mode_actions.items():
            action.setChecked(mode==(self.config.audio_spoken,self.config.audio_show_subtitles))
        for value,action in self.subtitle_delay_actions.items():
            action.setChecked(value==self.config.audio_subtitle_delay_ms)
        self.speaker_action.setChecked(self.config.audio_speaker_labels)

    def set_audio_mode(self,spoken,subtitles):
        self.set_audio_option("audio_show_subtitles",subtitles)
        self.set_audio_option("audio_spoken",spoken)

    def set_audio_option(self,name,value):
        self.config=replace(self.config,**{name:value})
        if name=="audio_show_subtitles" and self.audio_enabled:
            self.audio_display_token+=1
            if value and self.audio_overlay is None:self.open_audio_overlay()
            elif not value and self.audio_overlay:
                self.audio_overlay.clear();self.audio_overlay.close();self.audio_overlay.deleteLater()
                self.audio_overlay=None
        self.spoken_action.setChecked(self.config.audio_spoken)
        self.feedback_action.setChecked(self.config.audio_feedback_guard)
        self.match_voice_action.setChecked(self.config.audio_match_voice_range)
        self.local_voice_action.setChecked(self.config.audio_local_voices)
        self.sync_audio_controls()
        for rate,action in self.voice_rate_actions.items():action.setChecked(rate==self.config.audio_voice_rate)
        voice_related=name not in {"audio_show_subtitles","audio_speaker_labels","audio_subtitle_delay_ms"}
        if self.voice_session and voice_related:
            self.voice_restart_pending=self.audio_enabled and self.config.audio_spoken
            self.voice_session.stop()
        elif voice_related and self.audio_enabled and self.config.audio_spoken:
            self.start_voice()

    def populate_voices(self):
        from .voice import cached_voices,voices_for
        self.voice_menu.clear()
        for gender in ("Female","Male"):
            action=self.voice_menu.addAction("Default "+gender.lower()+" voice")
            action.triggered.connect(lambda checked=False,g=gender:self.set_default_voice(g))
        choices=voices_for(self.config.target,cached_voices())
        for voice in choices:
            name=voice["ShortName"]
            action=self.voice_menu.addAction(name+" ("+voice["Gender"]+", online)")
            action.setCheckable(True);action.setChecked(self.config.audio_voice==name)
            action.triggered.connect(lambda checked=False,n=name:self.set_online_voice(n))
        if not choices:
            self.voice_menu.addAction("Voice catalog loads when audio starts; some languages have no voice").setEnabled(False)

    def set_online_voice(self,name):
        self.config=replace(self.config,audio_local_voices=False)
        self.set_audio_option("audio_voice",name)

    def set_default_voice(self,gender):
        self.config=replace(self.config,audio_voice="",audio_voice_gender=gender,audio_match_voice_range=False,audio_local_voices=True)
        self.set_audio_option("audio_voice_gender",gender)

    def populate_voice_outputs(self):
        from .voice import output_devices
        self.voice_output_menu.clear()
        choices=[{"index":-1,"name":"Windows default output"}]
        try:choices+=output_devices()
        except Exception:
            self.voice_output_menu.addAction("Output device list unavailable").setEnabled(False)
        for device in choices:
            action=self.voice_output_menu.addAction(device["name"])
            action.setCheckable(True);action.setChecked(self.config.audio_output_device==device["index"])
            action.triggered.connect(lambda checked=False,i=device["index"]:self.set_audio_option("audio_output_device",i))

    def start_voice(self):
        if not self.config.audio_spoken or self.voice_session or not self.audio_enabled or self.exiting:return
        from .voice import VoiceSession
        self.voice_restart_pending=False
        self.voice_ready.clear()
        self.voice_session=VoiceSession(self.config,self.echo_gate,parent=self,ready_event=self.voice_ready)
        self.voice_session.state.connect(self.voice_state_changed)
        self.voice_session.failed.connect(self.voice_failed)
        self.voice_session.finished.connect(self.voice_stopped)
        self.voice_session.start()

    @Slot(str)
    def voice_state_changed(self,text):
        self.voice_status_action.setText("Voice: "+text)

    @Slot(str)
    def voice_failed(self,text):
        self.voice_status_action.setText(text)

    def voice_stopped(self):
        session,self.voice_session=self.voice_session,None
        if session:session.deleteLater()
        self.echo_gate.clear()
        if self.voice_restart_pending and self.audio_enabled and not self.exiting:self.start_voice()
        elif not self.audio_enabled or not self.config.audio_spoken:self.voice_status_action.setText("Voice: off")
        if self.exiting:self.finish_exit()

    @Slot(str)
    def audio_state_changed(self, state):
        if not self.audio_enabled:
            return
        self.audio_status = state
        self.audio_status_action.setText("Audio: "+state)
        if self.audio_overlay:
            self.audio_overlay.set_status(state)

    @Slot(str,str,float)
    def audio_subtitle(self, source, translated, pitch_hz=0.0):
        if self.audio_enabled and not self.exiting:
            if self.audio_overlay and self.config.audio_show_subtitles:
                label=self.voice_labels.label(pitch_hz) if self.config.audio_speaker_labels else ""
                token=self.audio_display_token
                def display():
                    if self.audio_enabled and token==self.audio_display_token and self.audio_overlay:
                        self.audio_overlay.set_subtitle(source,translated,label)
                if self.config.audio_subtitle_delay_ms:
                    QTimer.singleShot(self.config.audio_subtitle_delay_ms,display)
                else:display()
            if self.voice_session and self.config.audio_spoken:
                self.voice_session.enqueue(translated,pitch_hz)

    def audio_failed(self, message):
        self.stop_audio()
        self.audio_status = "Error: "+message
        self.audio_status_action.setText("Audio: "+message)
        self.status("Audio stopped: "+message,notify=True)

    def stop_audio(self):
        self.audio_enabled = False
        self.audio_display_token+=1
        self.voice_ready.set()
        self.voice_restart_pending = False
        if self.voice_session:
            self.voice_session.stop()
        if self.audio_session:
            self.audio_session.stop()
        if self.audio_overlay:
            self.audio_overlay.clear()
            self.audio_overlay.close()
            self.audio_overlay.deleteLater()
            self.audio_overlay = None
        for action in self.audio_actions.values():
            action.setChecked(False)
        self.audio_status = "Stopping..." if self.audio_session else "Off"
        self.audio_status_action.setText("Audio: "+self.audio_status)

    def audio_stopped(self):
        session,self.audio_session = self.audio_session,None
        if session:
            session.deleteLater()
        if self.audio_enabled:
            self.stop_audio()
        if not self.audio_status.startswith("Error:"):
            self.audio_status = "Off"
            self.audio_status_action.setText("Audio: off")
        if self.exiting:
            self.finish_exit()

    def bind_screen_signals(self):
        self.screen.geometryChanged.connect(self.display_changed)
        self.screen.logicalDotsPerInchChanged.connect(self.display_changed)

    def display_changed(self, *args):
        if self.exiting:
            return
        if self.selector:
            self.selector.cancel()
        self.stop_audio()
        self.clear()
        self.region = None
        if not self.display_pending:
            self.display_pending = True
            QTimer.singleShot(250, self.reconfigure_display)

    def reconfigure_display(self):
        if self.exiting:
            return
        try:
            screen = self.screen if self.screen in self.application.screens() else self.application.primaryScreen()
            if self.switch_screen(screen,force=True):
                self.status("Display changed. Select the area again.",notify=True)
        finally:
            self.display_pending = False

    def quit(self):
        self.exiting = True
        if self.model_download:
            process=self.model_download
            process.terminate()
            if not process.waitForFinished(2000):
                process.kill();process.waitForFinished(1000)
        self.floating_menu.close()
        self.menu.close()
        self.floating.close()
        self.stop_audio()
        self.timer.stop()
        self.clear_visuals()
        self.outline.clear()
        if self.selector:
            self.selector.close()
        self.hotkeys.close()
        self.status("Exiting...")
        if not self.busy and not self.initializing:
            self.thread.quit()

    def finish_exit(self):
        if self.exiting and not self.thread.isRunning() and self.audio_session is None and getattr(self,"voice_session",None) is None:
            self.tray.hide()
            self.capture.close()
            self.application.quit()

def run(config=None):
    require_windows()
    application = QApplication.instance() or QApplication([])
    from .fonts import load_fonts
    load_fonts()
    application.setApplicationName("HALO TEXT")
    application.setQuitOnLastWindowClosed(False)
    lock = QLockFile(str(STATE / "halo.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        from .ipc import request
        request("activate")
        return 0
    if not QSystemTrayIcon.isSystemTrayAvailable():
        raise RuntimeError("No Windows system tray is available in this session.")
    handler = RotatingFileHandler(STATE/"halo.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    config = config or load_config()
    from .ipc import CommandServer
    # Bind the control channel before starting a model worker. No event is
    # dispatched until the controller is assigned and the event loop starts.
    controller = None
    server = CommandServer(lambda command: controller.control(command), parent=application)
    try:
        controller = Controller(application, config)
        application._halo_controller = controller
        return application.exec()
    finally:
        server.close()
        lock.unlock()
