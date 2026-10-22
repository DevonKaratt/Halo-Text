from types import SimpleNamespace
import json
import pytest
from halo_text.config import Config
from halo_text.core import Box,TextBlock
from halo_text.source_language import detect,script_match


def test_ocr_language_catalog_routes_are_valid():
    from halo_text.languages import LANGUAGES
    from halo_text.ocr_packs import PACKS,LANGUAGE_PACK
    assert set(LANGUAGE_PACK).issubset(LANGUAGES)
    assert set(LANGUAGE_PACK.values()).issubset(PACKS)
    assert LANGUAGE_PACK["ru"]=="cyrillic"
    assert LANGUAGE_PACK["hi"]=="devanagari"

def test_confident_english_caption_does_not_wait_for_network_detection(monkeypatch):
    from halo_text import pipeline as module
    block=TextBlock("Welcome to our project.",Box(0,0,400,30),.99,30)
    reader=SimpleNamespace(last_source="en",source_confident=True,
                           recognize=lambda *args,**kwargs:[block])
    monkeypatch.setattr(module,"ScreenOCR",lambda config:reader)
    monkeypatch.setattr(module,"create_translator",lambda config:SimpleNamespace(
        translate_many=lambda texts:["translated"]*len(texts),last_hits=0))
    def forbidden(text):raise AssertionError("Unnecessary online detection")
    monkeypatch.setattr("halo_text.source_language.needs_google",forbidden)
    assert module.Pipeline(Config()).process(object()).translations[0].text=="translated"


def test_input_language_override_validation():
    assert Config(input_language="ru").input_language=="ru"
    assert Config(input_language="auto").input_language=="auto"
    with pytest.raises(ValueError,match="Unknown input language"):
        Config(input_language="xx")


def test_downloaded_ocr_pack_is_listed_and_removable(tmp_path,monkeypatch):
    from halo_text import ocr_packs,model_manager
    monkeypatch.setattr(ocr_packs,"MODELS",tmp_path)
    monkeypatch.setattr(model_manager,"MODELS",tmp_path)
    pack=tmp_path/"ocr-cyrillic"
    pack.mkdir()
    (pack/"halo-ocr.json").write_text(json.dumps({"pack":"cyrillic"}),encoding="utf-8")
    (pack/"demo_det.onnx").write_bytes(b"det")
    (pack/"demo_rec.onnx").write_bytes(b"rec")
    assert ocr_packs.installed("cyrillic")
    assert any(entry.key=="ocr:cyrillic" for entry in model_manager.installed_models())
    model_manager.remove_model("ocr:cyrillic","en")
    assert not pack.exists()


def test_cyrillic_source_detection_and_pack_filter():
    text="Добро пожаловать в наш проект."
    assert detect(text)=="ru"
    assert script_match(text,"cyrillic")>.9
    assert script_match(text,"latin")==0


def test_ukrainian_and_english_detection():
    assert detect("Ласкаво просимо до нашого проєкту!")=="uk"
    assert detect("Welcome to our project.")=="en"


def test_nonenglish_translation_requires_route_choice(monkeypatch):
    from halo_text import pipeline as module
    block=TextBlock("Добро пожаловать",Box(0,0,160,30),.99,30)
    class Reader:
        last_source="ru"
        def recognize(self,*args,**kwargs):return [block]
    monkeypatch.setattr(module,"ScreenOCR",lambda config:Reader())
    monkeypatch.setattr(module,"create_translator",lambda config:SimpleNamespace(translate_many=lambda texts:texts,last_hits=0))
    pipe=module.Pipeline(Config(target="en",backend="auto"))
    monkeypatch.setattr("halo_text.pair_models.find",lambda source,target:None)
    with pytest.raises(RuntimeError,match="SOURCE_CHOICE:ru:missing"):
        pipe.process(object())


def test_nonenglish_online_route_uses_detected_source(monkeypatch):
    from halo_text import pipeline as module
    block=TextBlock("Добро пожаловать",Box(0,0,160,30),.99,30)
    class Reader:
        last_source="ru"
        def recognize(self,*args,**kwargs):return [block]
    monkeypatch.setattr(module,"ScreenOCR",lambda config:Reader())
    monkeypatch.setattr(module,"create_translator",lambda config:SimpleNamespace(translate_many=lambda texts:texts,last_hits=0))
    monkeypatch.setattr("halo_text.pair_models.find",lambda source,target:None)
    seen=[]
    class Web:
        def __init__(self,config,source="en"):seen.append((source,config.target))
        def translate_many(self,texts):return ["Welcome"]
    monkeypatch.setattr("halo_text.online.WebTranslator",Web)
    pipe=module.Pipeline(Config(target="en",backend="auto"))
    pipe.source_routes["ru","en"]="web"
    result=pipe.process(object())
    assert seen==[("ru","en")]
    assert result.translations[0].text=="Welcome"


def test_google_language_identification_uses_recognized_text_only():
    from halo_text.online import detect_language
    class Response:
        def raise_for_status(self): pass
        def json(self): return [[], None, "es"]
    class Session:
        def get(self, endpoint, params, timeout):
            assert params["q"] == "Hola a todos"
            assert params["sl"] == "auto"
            assert timeout == (3, 5)
            return Response()
    assert detect_language("Hola a todos", Session()) == "es"


def test_detected_source_requires_ocr_pack_before_translation(monkeypatch):
    from halo_text import pipeline as module
    block=TextBlock("Hola a todos",Box(0,0,160,30),.99,30)
    class Reader:
        last_source="en"
        def recognize(self,*args,**kwargs):return [block]
    monkeypatch.setattr(module,"ScreenOCR",lambda config:Reader())
    monkeypatch.setattr(module,"create_translator",lambda config:SimpleNamespace(translate_many=lambda texts:texts,last_hits=0))
    monkeypatch.setattr("halo_text.source_language.needs_google",lambda text:True)
    monkeypatch.setattr("halo_text.online.detect_language",lambda text:"es")
    monkeypatch.setattr("halo_text.ocr_packs.installed",lambda pack:False)
    pipe=module.Pipeline(Config(target="en",backend="auto"))
    with pytest.raises(RuntimeError,match="OCR_PACK_CHOICE:es:latin"):
        pipe.process(object())
