"""CPU local Hindi synthesis with preloaded stock male/female models."""
import io,json,wave
from pathlib import Path
import numpy as np
from .paths import ROOT
from .voice_setup import model_path,installed
class LocalVoice:
    def __init__(self,threads=2):
        if not installed():raise RuntimeError("Install local Hindi voices: app/run.py --install-voices")
        import onnxruntime as ort
        from piper import PiperVoice
        from piper.config import PiperConfig
        self.voices={}
        for gender in ("Male","Female"):
            path=model_path(gender);options=ort.SessionOptions()
            options.intra_op_num_threads=threads;options.inter_op_num_threads=1
            self.voices[gender]=PiperVoice(session=ort.InferenceSession(str(path),sess_options=options,providers=["CPUExecutionProvider"]),config=PiperConfig.from_dict(json.loads(Path(str(path)+".json").read_text(encoding="utf-8"))),download_dir=ROOT/"runtime/cache")
            self.synthesize("नमस्ते",gender)
    def synthesize(self,text,gender="Female",rate=50,pitch=0):
        from piper.config import SynthesisConfig
        voice=self.voices[gender]
        reference=200 if gender=="Female" else 120
        factor=max(.8,min(1.2,(reference+pitch)/reference))
        config=SynthesisConfig(length_scale=factor/(1+rate/100))
        chunks=list(voice.synthesize(text,syn_config=config))
        if not chunks:raise RuntimeError("Local voice returned no audio")
        output=io.BytesIO()
        with wave.open(output,"wb") as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(round(chunks[0].sample_rate*factor))
            wav.writeframes(b"".join(c.audio_int16_bytes for c in chunks))
        return output.getvalue()
