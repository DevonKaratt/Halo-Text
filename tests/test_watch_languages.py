from types import SimpleNamespace
import pytest
from halo_text.config import Config
from halo_text.languages import LANGUAGES,language
from halo_text.core import Box
from halo_text.capture import ScreenMapping
from halo_text.online import WebTranslator,route

def test_language_catalog_has_22_indian_and_30_global_targets_plus_english():
    assert len(LANGUAGES)==53
    assert sum(l.group=="Indian" for l in LANGUAGES.values())==22
    assert sum(l.group=="Global" for l in LANGUAGES.values())==31
    assert all(language(c).group=="Indian" for c in ("ta","te","brx","ks","sat","mni-Mtei"))

def test_local_backend_never_silently_sends_text_online(monkeypatch):
    monkeypatch.setattr("halo_text.model_setup.find_model",lambda code:None)
    monkeypatch.setattr("halo_text.indic_setup.installed",lambda:False)
    assert route(Config(target="ta",backend="local"))=="missing"
    assert route(Config(target="ta",backend="auto"))=="web"
    assert route(Config(target="brx",backend="auto"))=="missing"

def test_missing_indian_language_can_be_selected_for_download(monkeypatch):
    from halo_text.app import Controller
    monkeypatch.setattr("halo_text.model_setup.find_model",lambda code:None)
    monkeypatch.setattr("halo_text.indic_setup.installed",lambda:False)
    messages=[]
    state=SimpleNamespace(config=Config(target="hi",backend="auto"),ready=True,exiting=False,
                          selector=None,overlay=SimpleNamespace(config=None),
                          clear=lambda:None,status=lambda message,**kwargs:messages.append(message))
    Controller.change_language(state,"brx")
    assert state.config.target=="brx" and state.overlay.config.target=="brx"
    assert "Download offline model" in messages[-1]

def test_online_response_preserves_each_screen_block():
    translator=WebTranslator(Config(target="ta"))
    seen=[]
    def get(url,**kwargs):
        seen.append(kwargs["params"])
        return SimpleNamespace(status_code=200,raise_for_status=lambda:None,
            json=lambda:[[[kwargs["params"]["q"]+" translated"]]])
    translator.session=SimpleNamespace(get=get)
    translator.next_request=0
    assert translator.translate_many(["First block"])==["First block translated"]
    assert seen[0]["sl"]=="en" and seen[0]["tl"]=="ta"

def test_online_rate_limit_is_not_treated_as_translation():
    translator=WebTranslator(Config(target="ta"))
    translator.session=SimpleNamespace(get=lambda *a,**k:SimpleNamespace(status_code=429))
    with pytest.raises(RuntimeError,match="limit"):
        translator.translate_many(["Hello"])

def test_online_empty_response_is_rejected():
    translator=WebTranslator(Config(target="ta"))
    translator.session=SimpleNamespace(get=lambda *a,**k:SimpleNamespace(
        status_code=200,raise_for_status=lambda:None,json=lambda:[[]]))
    with pytest.raises(RuntimeError,match="invalid"):
        translator.translate_many(["Hello"])

def test_persistent_outline_maps_region_and_pause_does_not_hide(qapp,monkeypatch):
    from halo_text.outline import SelectionOutline
    monkeypatch.setattr("halo_text.outline.exclude_from_capture",lambda handle:True)
    outline=SelectionOutline(qapp.primaryScreen())
    try:
        outline.set_region(ScreenMapping(0,0,1920,1080,1280,720),Box(150,150,600,300),True)
        assert outline.isVisible() and outline.area.x()==100 and outline.area.width()==400
        outline.set_watching(False)
        assert outline.isVisible() and not outline.watching
        outline.clear()
        assert not outline.isVisible() and outline.area is None
    finally:
        outline.close()

def test_region_release_enables_watch_and_preserves_outline():
    from halo_text.app import Controller
    state=SimpleNamespace(
        config=Config(follow_window=False),capture=SimpleNamespace(mapping=ScreenMapping(0,0,800,600,800,600)),
        selector=None,auto=False,wanted=False)
    calls=[]
    state.invalidate=lambda:calls.append("invalidate")
    state.set_auto=lambda enabled:setattr(state,"auto",enabled)
    state.show_outline=lambda:calls.append("outline")
    state.status=lambda *args,**kwargs:None
    from PySide6.QtCore import QRect
    Controller.region_selected(state,QRect(10,20,400,200))
    assert state.auto and state.wanted and state.region==Box(10,20,400,200)
    assert calls==["invalidate","outline"]

def test_rtl_language_metadata():
    assert all(language(code).rtl for code in ("ar","ur","ks","sd","fa","ps"))
    assert not language("ta").rtl

def test_translation_error_pauses_but_restores_selection_outline():
    from halo_text.app import Controller
    calls=[]
    state=SimpleNamespace(generation=1,exiting=False,config=Config(),overlay=SimpleNamespace(items=[]),
        clear=lambda:calls.append("clear"),
        show_outline=lambda:calls.append("outline"),
        status=lambda *args,**kwargs:None)
    Controller.failed(state,1,"Online unavailable")
    assert calls==["clear","outline"] and not state.busy

def test_online_rate_limit_keeps_automatic_watching_on():
    from time import monotonic
    from halo_text.app import Controller
    calls=[]
    state=SimpleNamespace(generation=1,exiting=False,config=Config(),auto=True,
        online_retry_after=0.0,overlay=SimpleNamespace(items=[]),
        clear=lambda:calls.append("clear"),show_outline=lambda:calls.append("outline"),
        status=lambda message,**kwargs:calls.append(message))
    Controller.failed(state,1,"Online translation limit reached. Watching paused; retry later.")
    assert state.auto and state.online_retry_after>monotonic()
    assert "clear" not in calls and "outline" not in calls

def test_auto_route_prefers_existing_offline_model(monkeypatch):
    monkeypatch.setattr("halo_text.model_setup.find_model",lambda code:object())
    assert route(Config(target="hi",backend="auto"))=="local"

def test_shared_model_covers_all_indian_outputs_including_malayalam(monkeypatch):
    from halo_text.indic_setup import TARGET_TAGS
    monkeypatch.setattr("halo_text.model_setup.find_model",lambda code:None)
    monkeypatch.setattr("halo_text.indic_setup.installed",lambda:True)
    assert set(TARGET_TAGS)=={code for code,item in LANGUAGES.items() if item.group=="Indian"}
    assert all(route(Config(target=code,backend="auto"))=="indic" for code in TARGET_TAGS)
