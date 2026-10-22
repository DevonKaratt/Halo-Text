import json
import zipfile
from types import SimpleNamespace
import numpy as np
import pytest
from halo_text.capture import mapping_for_screen, ScreenCapture
from halo_text.config import Config
from halo_text.core import Box,TextBlock,Translation
from halo_text.model_setup import extract_package

def screen(name,width,height):
    return SimpleNamespace(name=lambda:name,geometry=lambda:SimpleNamespace(width=lambda:width,height=lambda:height))

def test_mixed_dpi_left_monitor_matches_by_device_name():
    monitors=[{"name":"DISPLAY1","left":0,"top":0,"width":1920,"height":1080},
              {"name":"DISPLAY2","left":-2560,"top":-300,"width":2560,"height":1440}]
    mapping=mapping_for_screen(screen("display2",1707,960),monitors)
    assert (mapping.left,mapping.top)==(-2560,-300)
    assert mapping.to_physical((0,0,1707,960))==Box(0,0,2560,1440)
    assert mapping.to_physical((100,100,200,100))==Box(150,150,300,150)

def test_unknown_monitor_never_silently_captures_primary():
    monitors=[{"name":"A"},{"name":"B"}]
    with pytest.raises(RuntimeError,match="map"):
        mapping_for_screen(screen("C",100,100),monitors)

def test_capture_applies_negative_monitor_origin():
    from halo_text.capture import ScreenMapping
    capture=ScreenCapture.__new__(ScreenCapture)
    capture.mapping=ScreenMapping(-1920,-200,1920,1080,1280,720)
    seen=[]
    def grab(rect):
        seen.append(rect)
        return np.zeros((rect["height"],rect["width"],4),np.uint8)
    capture.sct=SimpleNamespace(grab=grab)
    capture.grab(Box(150,100,200,80))
    assert seen==[{"left":-1770,"top":-100,"width":200,"height":80}]
    with pytest.raises(ValueError):
        capture.grab(Box(-1,0,100,100))

def test_unsupported_language_rejected():
    with pytest.raises(ValueError,match="Unknown target language"):
        Config(target="unknown")

def test_archive_cannot_escape_project_staging(tmp_path):
    archive=tmp_path/"bad.zip"
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("../escaped.txt","bad")
    with pytest.raises(ValueError,match="Unsafe"):
        extract_package(archive,tmp_path/"stage","es")
    assert not (tmp_path/"escaped.txt").exists()

def test_wrong_language_archive_never_installs(tmp_path):
    archive=tmp_path/"wrong.zip"
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("model/metadata.json",json.dumps({"from_code":"en","to_code":"fr"}))
        z.writestr("model/sentencepiece.model","dummy")
        z.writestr("model/model/model.bin","dummy")
    with pytest.raises(RuntimeError,match="expected"):
        extract_package(archive,tmp_path/"stage","es")

def test_original_toggle_does_not_restore_cleared_content(qapp,monkeypatch):
    from halo_text.overlay import Overlay
    from halo_text.capture import ScreenMapping
    monkeypatch.setattr("halo_text.overlay.exclude_from_capture",lambda handle:True)
    overlay=Overlay(qapp.primaryScreen(),Config())
    mapping=ScreenMapping(0,0,800,600,800,600)
    block=Translation(TextBlock("Welcome",Box(10,10,400,50),1,40),"आपका स्वागत है")
    try:
        overlay.show_translations([block],mapping,Box(0,0,800,600))
        assert overlay.isVisible()
        overlay.set_original_visible(True)
        assert not overlay.isVisible() and overlay.items
        overlay.show_translations([block],mapping,Box(0,0,800,600))
        assert not overlay.isVisible()
        overlay.set_original_visible(False)
        assert overlay.isVisible()
        overlay.set_original_visible(True)
        overlay.clear()
        overlay.set_original_visible(False)
        assert not overlay.isVisible() and not overlay.items
    finally:
        overlay.close()

def test_failed_language_load_keeps_previous_engine(qapp,monkeypatch):
    from halo_text.app import Worker
    previous=object()
    worker=Worker(Config())
    worker.pipeline=SimpleNamespace(translator=previous)
    failures=[]
    worker.language_failed.connect(failures.append)
    def fail(config):
        raise RuntimeError("model unavailable")
    monkeypatch.setattr("halo_text.translation.create_translator",fail)
    worker.change_language(Config(target="es"))
    assert worker.pipeline.translator is previous
    assert worker.config.target=="hi" and len(failures)==1

def test_successful_language_load_replaces_cache(qapp,monkeypatch):
    from halo_text.app import Worker
    replacement=SimpleNamespace(translate_many=lambda texts:["Bienvenido"]*len(texts))
    worker=Worker(Config())
    worker.pipeline=SimpleNamespace(translator=object())
    ready=[]
    worker.language_ready.connect(ready.append)
    monkeypatch.setattr("halo_text.translation.create_translator",lambda config:replacement)
    worker.change_language(Config(target="es"))
    assert worker.pipeline.translator is replacement
    assert ready[0].target=="es"

@pytest.mark.parametrize("target,text",[("es","Bienvenido a nuestro proyecto."),
                                        ("fr","Bienvenue dans notre projet.")])
def test_latin_target_renders_and_fits(qapp,target,text):
    from halo_text.overlay import prepare_paint_blocks
    items,skipped=prepare_paint_blocks([Translation(
        TextBlock("Welcome",Box(10,10,500,60),1,36),text)],Config(target=target))
    assert len(items)==1 and skipped==0


def test_chinese_package_code_maps_to_catalog_code(tmp_path,monkeypatch):
 from halo_text import model_setup
 archive=tmp_path/'chinese.zip'
 with zipfile.ZipFile(archive,'w') as z:
  z.writestr('translate-en_zh/metadata.json',json.dumps({'from_code':'en','to_code':'zh'}))
  z.writestr('translate-en_zh/sentencepiece.model',b'tokenizer')
  z.writestr('translate-en_zh/model/model.bin',b'weights')
 base=model_setup.extract_package(archive,tmp_path/'staging','zh-CN')
 monkeypatch.setattr(model_setup,'MODELS',tmp_path/'staging')
 assert model_setup.find_model('zh-CN')==base
