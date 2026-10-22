"""Conservative source-language identification for short OCR text."""
from collections import Counter
import unicodedata

SCRIPT_SOURCE = {
    "CYRILLIC": "ru", "ARABIC": "ar", "DEVANAGARI": "hi",
    "TAMIL": "ta", "TELUGU": "te", "KANNADA":"kn", "THAI": "th", "HANGUL": "ko",
    "HIRAGANA": "ja", "KATAKANA": "ja", "CJK": "zh-CN",
}
PACK_SCRIPT = {
    "cyrillic": {"CYRILLIC"}, "arabic": {"ARABIC"},
    "devanagari": {"DEVANAGARI"}, "tamil": {"TAMIL"},
    "telugu": {"TELUGU"}, "kannada":{"KANNADA"}, "thai": {"THAI"},
    "korean": {"HANGUL"}, "japanese": {"HIRAGANA", "KATAKANA", "CJK"},
    "chinese": {"CJK"}, "latin": {"LATIN"},
}


def script(text):
    letters = [unicodedata.name(ch, "").split(" ")[0] for ch in text if ch.isalpha()]
    return Counter(letters).most_common(1)[0][0] if letters else None


def script_match(text, pack):
    letters = [unicodedata.name(ch, "").split(" ")[0] for ch in text if ch.isalpha()]
    if len(letters) < 2:
        return 0.0
    return sum(item in PACK_SCRIPT[pack] for item in letters) / len(letters)


def detect(text):
    """Return a likely ISO source code; short or ambiguous Latin text defaults to English."""
    current = script(text)
    if current == "CYRILLIC":
        if any(ch in text for ch in "іїєґІЇЄҐ"):
            return "uk"
    if current in SCRIPT_SOURCE:
        default = SCRIPT_SOURCE[current]
    else:
        default = "en"
    letters = sum(ch.isalpha() for ch in text)
    if letters < 12:
        return default
    try:
        from langdetect import DetectorFactory, detect_langs
        DetectorFactory.seed = 0
        candidates = detect_langs(text)
        if candidates and candidates[0].prob >= 0.85:
            code = candidates[0].lang
            if code == "zh-cn" or code == "zh-tw":
                code = "zh-CN"
            if current == "LATIN" and code in {"en", "es", "fr", "pt", "de", "it", "id", "tr", "vi", "pl", "sw", "tl", "ms", "uz"}:
                return code
            if current != "LATIN" and code in {"ru", "uk", "ar", "fa", "hi", "ne", "ta", "te", "th", "ko", "ja", "zh-CN"}:
                return code
    except (ImportError, ValueError):
        pass
    return default


def needs_google(text):
    """Only ambiguous readable text merits a network language check."""
    if sum(ch.isalpha() for ch in text) < 8:
        return False
    current = script(text)
    if current not in {"LATIN", "CYRILLIC", "ARABIC", "DEVANAGARI", "CJK"}:
        return False
    try:
        from langdetect import DetectorFactory, detect_langs
        DetectorFactory.seed = 0
        candidates = detect_langs(text)
        return not candidates or candidates[0].prob < .85
    except (ImportError, ValueError):
        return True
