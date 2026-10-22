from dataclasses import dataclass
from time import perf_counter
import re
from .core import Translation
from .ocr import ScreenOCR
from .translation import create_translator

@dataclass
class PipelineResult:
    translations: list
    metrics: dict
    source: str = "en"

class Pipeline:
    def __init__(self, config):
        self.config = config
        self.ocr = ScreenOCR(config)
        self.translator = create_translator(config)
        self.source_translators = {}
        self.source_routes = {}
        self.language_checks = {}

    def warmup(self):
        import cv2
        import numpy as np
        sample = np.full((120, 640, 3), 255, np.uint8)
        cv2.putText(sample, "Welcome to our project.", (20, 75),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA)
        blocks = self.ocr.recognize(sample)
        if not blocks:
            raise RuntimeError("OCR warm-up failed to recognize the generated sample.")
        # Load and exercise the chosen local engine before reporting Ready.
        # Online routes retain their normal request behavior; no startup network call.
        if hasattr(self.translator.backend,"engine"):
            self.translator.translate_many(["Welcome to our project."])
        return " ".join(block.text for block in blocks)

    def process(self, image, fast_captions=False):
        start = perf_counter()
        blocks = self.ocr.recognize(image,fast_captions=fast_captions)
        ocr_end = perf_counter()
        source = self.ocr.last_source
        if (blocks and self.config.input_language == "auto"
                and not getattr(self.ocr,"source_confident",False)):
            from .source_language import needs_google
            text = " ".join(block.text for block in blocks)
            if needs_google(text):
                from .online import detect_language
                if text not in self.language_checks:
                    try:
                        self.language_checks[text] = detect_language(text)
                    except RuntimeError:
                        self.language_checks[text] = None
                    if len(self.language_checks) > 128:
                        self.language_checks.pop(next(iter(self.language_checks)))
                source = self.language_checks[text] or source
        if blocks and source != "en" and source != self.config.target:
            from .ocr_packs import LANGUAGE_PACK, installed
            pack = LANGUAGE_PACK.get(source)
            if pack and not installed(pack):
                raise RuntimeError(f"OCR_PACK_CHOICE:{source}:{pack}")
        texts = [b.text for b in blocks]
        def translate(backend):
            if not fast_captions:
                return backend.translate_many(texts)
            # Only complete sentences are reused independently. Translating an
            # arbitrary changed word would lose context and break word order.
            pieces = [re.split(r"(?<=[.!?。！？])\s+", value.strip()) for value in texts]
            flat = [part for group in pieces for part in group]
            rendered = iter(backend.translate_many(flat))
            return [" ".join(next(rendered) for _ in group) for group in pieces]
        if source == self.config.target:
            output = [block.text for block in blocks]
        elif source == "en":
            output = translate(self.translator)
        else:
            from .pair_models import find
            from .translation import LocalTranslator, CachedTranslator
            from .online import WebTranslator
            pair = (source, self.config.target)
            local = find(*pair)
            choice = self.source_routes.get(pair)
            if choice is None:
                raise RuntimeError(f"SOURCE_CHOICE:{source}:{'installed' if local else 'missing'}")
            if choice == "local" and not local:
                raise RuntimeError(f"OFFLINE_PAIR_MISSING:{source}:{self.config.target}")
            cache_key = (source,self.config.target,choice)
            if cache_key not in self.source_translators:
                backend = LocalTranslator(self.config, source) if choice == "local" else WebTranslator(self.config, source=source)
                self.source_translators[cache_key] = CachedTranslator(backend, self.config.cache_size)
            output = translate(self.source_translators[cache_key])
        end = perf_counter()
        return PipelineResult(
            [Translation(block, text) for block, text in zip(blocks, output)],
            {"ocr_ms": round((ocr_end-start)*1000,1),
             "translation_ms": round((end-ocr_end)*1000,1),
             "total_ms": round((end-start)*1000,1),
             "fast_captions": fast_captions, "blocks": len(blocks), "source": source,
             "cache_hits": self.translator.last_hits if source == "en" else 0},
            source,
        )


def preload_runtime():
    # Load AI libraries before Qt installs its Python feature-import hook.
    # Model construction and inference still run on the worker thread.
    from rapidocr import RapidOCR
    import ctranslate2
    import sentencepiece

    try:
        import piper
    except ImportError:
        pass
    try:
        import faster_whisper
    except ImportError:
        pass  # Text translation can run without the optional speech dependencies.
