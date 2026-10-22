import json
from dataclasses import dataclass, fields
from .paths import ROOT

@dataclass(frozen=True)
class Config:
    backend: str = "local"
    target: str = "hi"
    input_language: str = "auto"
    auto_on_select: bool = True
    floating_icon: bool = True
    fast_captions: bool = False
    caption_hold: bool = True
    follow_window: bool = True
    audio_source: str = "system"
    audio_cpu_threads: int = 2
    audio_max_seconds: int = 3
    audio_spoken: bool = True
    audio_show_subtitles: bool = True
    audio_speaker_labels: bool = True
    audio_subtitle_delay_ms: int = 0
    audio_match_voice_range: bool = True
    audio_local_voices: bool = True
    audio_voice: str = ""
    audio_voice_gender: str = "Female"
    audio_voice_rate: int = 50
    audio_voice_pitch: int = 0
    audio_output_device: int = -1
    audio_feedback_guard: bool = True
    audio_energy_threshold: float = 0.006
    cpu_threads: int = 4
    ocr_confidence: float = 0.60
    max_image_edge: int = 1600
    max_blocks: int = 35
    capture_interval_ms: int = 350
    settle_ms: int = 700
    auto_interval_ms: int = 1800
    min_font_px: int = 11
    max_font_px: int = 32
    cache_size: int = 2000
    groq_model: str = "openai/gpt-oss-20b"

    def __post_init__(self):
        from .languages import language,LANGUAGES
        language(self.target)
        if self.input_language != "auto" and self.input_language not in LANGUAGES:
            raise ValueError("Unknown input language")
        if type(self.fast_captions) is not bool:
            raise ValueError("fast_captions must be true or false")
        if type(self.floating_icon) is not bool:
            raise ValueError("floating_icon must be true or false")
        if type(self.auto_on_select) is not bool:
            raise ValueError("auto_on_select must be true or false")
        if any(type(v) is not bool for v in (self.audio_spoken,self.audio_feedback_guard,self.audio_match_voice_range,self.audio_local_voices,self.audio_show_subtitles,self.audio_speaker_labels,self.caption_hold,self.follow_window)):
            raise ValueError("Audio spoken/feedback settings must be boolean")
        if self.audio_voice_gender not in ("Male","Female") or not isinstance(self.audio_voice,str):
            raise ValueError("Invalid speech voice preference")
        if type(self.audio_output_device) is not int or self.audio_output_device < -1:
            raise ValueError("Invalid speech output device")
        if self.audio_source not in ("system","microphone"):
            raise ValueError("audio_source must be system or microphone")
        if (type(self.audio_energy_threshold) not in (int,float)
                or not .0001 <= self.audio_energy_threshold <= .1):
            raise ValueError("audio_energy_threshold must be between .0001 and .1")
        if self.backend not in ("local", "groq", "auto", "web"):
            raise ValueError("backend must be local, auto, web, or groq")
        limits = {
            "audio_voice_rate": (-30, 60), "audio_voice_pitch": (-30, 30),
            "audio_cpu_threads": (1, 8), "audio_max_seconds": (1, 12),
            "cpu_threads": (1, 16), "max_image_edge": (640, 3200),
            "max_blocks": (1, 100), "capture_interval_ms": (150, 5000),
            "settle_ms": (200, 5000), "auto_interval_ms": (500, 60000),
            "min_font_px": (8, 24), "max_font_px": (12, 64),
            "cache_size": (1, 10000),
            "audio_subtitle_delay_ms": (0, 3000),
        }
        for key, (low, high) in limits.items():
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{key} must be an integer from {low} to {high}")
        if not isinstance(self.ocr_confidence, (int, float)) or not 0 <= self.ocr_confidence <= 1:
            raise ValueError("ocr_confidence must be between zero and one")
        if self.min_font_px > self.max_font_px:
            raise ValueError("min_font_px must be <= max_font_px")
    def watch_timing(self):
        """Short caption scheduling without changing the document timing settings."""
        if self.fast_captions:
            return (50,0,100)
        return (self.capture_interval_ms,self.settle_ms,self.auto_interval_ms)


def load_config():
    data = {}
    for filename in ("config.json", "config.local.json"):
        path = ROOT / "settings" / filename
        if path.exists():
            data.update(json.loads(path.read_text(encoding="utf-8")))
    known = {f.name for f in fields(Config)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"Unknown config options: {', '.join(sorted(unknown))}")
    return Config(**data)
