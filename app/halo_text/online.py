"""User-approved Google Translate web adapter; sends text, never screenshots."""
import time
import requests
from .core import normalize
from .languages import language, LANGUAGES

def detect_language(text, session=None):
    """Ask Google's keyless text endpoint to identify already-recognized text."""
    text = normalize(text)
    if not text or len(text) > 4500:
        raise ValueError("No suitable text to identify")
    client = session or requests
    try:
        response = client.get(WebTranslator.endpoint, params={
            "client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": text,
        }, timeout=(3, 5))
        response.raise_for_status()
        code = response.json()[2]
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Google language identification is unavailable") from exc
    aliases = {"zh-cn": "zh-CN", "zh-tw": "zh-CN", "fil": "tl", "iw": "he"}
    code = aliases.get(str(code).lower(), str(code).lower())
    return code if code in LANGUAGES else None

class WebTranslator:
    """Keyless public endpoint; this is not the paid Google Cloud API."""
    endpoint="https://translate.googleapis.com/translate_a/single"
    def __init__(self,config,source="en"):
        self.target=language(config.target).code
        self.source=source
        if self.target in {"brx","ks"} and source=="en":
            raise RuntimeError("This language needs the local Indian pack. Run: app/run.py --install-indic")
        self.session=requests.Session()
        self.next_request=0.0

    def translate_many(self,texts):
        results=[]
        for text in texts:
            source=normalize(text)
            if len(source)>4500:
                raise RuntimeError("Online text block is too long. Select a smaller area.")
            wait=self.next_request-time.monotonic()
            if wait>0:
                time.sleep(wait)
            try:
                response=self.session.get(self.endpoint,params={
                    "client":"gtx","sl":self.source,"tl":self.target,"dt":"t","q":source},timeout=(8,20))
                self.next_request=time.monotonic()+.25
                if response.status_code==429:
                    raise RuntimeError("Online translation limit reached. Watching paused; retry later.")
                if response.status_code in (400,403):
                    raise RuntimeError("The online service rejected this language or request.")
                response.raise_for_status()
                data=response.json()
                pieces=data[0]
                if not isinstance(pieces,list):
                    raise ValueError("Invalid response")
                translated="".join(part[0] for part in pieces if isinstance(part,list) and part and isinstance(part[0],str)).strip()
                if not translated:
                    raise ValueError("Empty translation")
            except requests.RequestException as exc:
                raise RuntimeError("Online translation unavailable. Check your connection or choose an offline language.") from exc
            except (ValueError,KeyError,IndexError,TypeError) as exc:
                raise RuntimeError("Online service returned an invalid translation.") from exc
            results.append(translated)
        return results

def route(config):
    from .model_setup import find_model
    from .indic_setup import installed as indic_installed, TARGET_TAGS
    language(config.target)
    if config.backend=="groq":
        return "groq"
    if config.backend=="web":
        return "web" if config.target not in {"brx","ks"} else "missing"
    if find_model(config.target):
        return "local"
    if config.target in TARGET_TAGS and indic_installed():
        return "indic"
    if config.backend=="auto" and config.target not in {"brx","ks"}:
        return "web"
    return "missing"
