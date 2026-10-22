"""Optional, removable RapidOCR recognition packs kept inside HALO/models."""
import json
from pathlib import Path
from .paths import MODELS, configure

# One recognition pack can cover several languages sharing a writing system.
# These are the routes exposed by the pinned RapidOCR 3.10 model catalogue.
PACKS = {
    "cyrillic": ("Cyrillic (Russian, Ukrainian)", "PP-OCRv5", "cyrillic"),
    "latin": ("Latin script (Spanish, French, Portuguese and others)", "PP-OCRv5", "latin"),
    "arabic": ("Arabic script", "PP-OCRv5", "arabic"),
    "devanagari": ("Devanagari (Hindi and related languages)", "PP-OCRv5", "devanagari"),
    "tamil": ("Tamil script", "PP-OCRv5", "ta"),
    "telugu": ("Telugu script", "PP-OCRv5", "te"),
    "kannada": ("Kannada script", "PP-OCRv4", "ka"),
    "thai": ("Thai script", "PP-OCRv5", "th"),
    "korean": ("Korean script", "PP-OCRv5", "korean"),
    "chinese": ("Chinese script", "PP-OCRv5", "ch"),
    "japanese": ("Japanese script", "PP-OCRv4", "japan"),
}

# Map catalogue languages to an OCR writing-system route. A shared script pack
# does not imply perfect language identification for every language using it.
LANGUAGE_PACK = {
    "brx":"devanagari", "doi":"devanagari", "hi":"devanagari",
    "gom":"devanagari", "mai":"devanagari", "mr":"devanagari",
    "ne":"devanagari", "sa":"devanagari", "ks":"arabic",
    "sd":"arabic", "ur":"arabic", "ta":"tamil", "te":"telugu", "kn":"kannada",
    "zh-CN":"chinese", "es":"latin", "ar":"arabic", "fr":"latin",
    "pt":"latin", "id":"latin", "ru":"cyrillic", "de":"latin",
    "ja":"japanese", "vi":"latin", "sw":"latin", "ha":"latin",
    "tr":"latin", "tl":"latin", "yue":"chinese", "fa":"arabic",
    "ko":"korean", "th":"thai", "jv":"latin", "it":"latin",
    "yo":"latin", "ps":"arabic", "uz":"latin", "ms":"latin",
    "ig":"latin", "om":"latin", "pl":"latin", "uk":"cyrillic",
}


def folder(key):
    if key not in PACKS:
        raise ValueError("Unsupported OCR pack")
    return MODELS / ("ocr-" + key)


def installed(key):
    base = folder(key)
    marker = base / "halo-ocr.json"
    try:
        info = json.loads(marker.read_text(encoding="utf-8"))
        return (info.get("pack") == key and
                any(base.glob("*rec*.onnx")) and any(base.glob("*det*.onnx")))
    except (OSError, ValueError):
        return False


def engine(key, config):
    """Create an engine only for a pack already installed by the user."""
    if not installed(key):
        raise RuntimeError(f"OCR pack {key} is not installed")
    return _engine(key, config)


def _engine(key, config):
    from rapidocr import RapidOCR, OCRVersion, ModelType
    _, version, language = PACKS[key]
    return RapidOCR(params={
        "Global.log_level": "warning", "Global.use_cls": False,
        "Global.model_root_dir": str(folder(key)),
        "Det.ocr_version": OCRVersion(version), "Det.model_type": ModelType.MOBILE,
        "Det.limit_type": "max", "Det.limit_side_len": config.max_image_edge,
        "Rec.ocr_version": OCRVersion(version), "Rec.model_type": ModelType.MOBILE,
        "Rec.lang_type": language,
        "EngineConfig.onnxruntime.intra_op_num_threads": config.cpu_threads,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    })


def install(key):
    if key not in PACKS:
        raise ValueError("Unsupported OCR pack")
    configure()
    if installed(key):
        return folder(key)
    import numpy as np
    import cv2
    base = folder(key)
    base.mkdir(parents=True, exist_ok=True)
    from .config import load_config
    reader = _engine(key, load_config())
    sample=np.full((96, 400, 3), 255, dtype=np.uint8)
    cv2.putText(sample,"HALO TEXT",(18,65),cv2.FONT_HERSHEY_SIMPLEX,1.4,(0,0,0),3,cv2.LINE_AA)
    reader(sample, use_cls=False)
    if not (any(base.glob("*rec*.onnx")) and any(base.glob("*det*.onnx"))):
        raise RuntimeError("OCR model download did not complete")
    (base / "halo-ocr.json").write_text(
        json.dumps({"pack": key, "version": PACKS[key][1], "language_route": PACKS[key][2]}, indent=2),
        encoding="utf-8")
    (base / "README.md").write_text(
        f"# {PACKS[key][0]} OCR pack\n\n"
        "ONNX text detection and recognition weights downloaded by RapidOCR from its versioned ModelScope catalogue. "
        "halo-ocr.json identifies the pack. Remove it using H > Downloaded language models; it can be downloaded again. "
        "Upstream model license and attribution: https://rapidai.github.io/RapidOCRDocs/main/en/model_list/\n",
        encoding="utf-8")
    return base
