import pytest
from halo_text.translation import CachedTranslator, GroqTranslator
from halo_text.config import Config

class FakeBackend:
    def __init__(self):
        self.calls = []
    def translate_many(self,texts):
        self.calls.append(texts)
        return ["Hindi:"+t for t in texts]

def test_repeated_screen_text_is_not_sent_twice():
    backend = FakeBackend()
    cached = CachedTranslator(backend,2)
    assert cached.translate_many(["Hello","Hello","World"]) == ["Hindi:Hello","Hindi:Hello","Hindi:World"]
    assert backend.calls == [["Hello","World"]]
    cached.translate_many(["Hello"])
    assert len(backend.calls) == 1

def test_response_survives_batch_larger_than_cache():
    cached = CachedTranslator(FakeBackend(),1)
    assert cached.translate_many(["one","two","one"]) == ["Hindi:one","Hindi:two","Hindi:one"]

def test_cache_hits_count_only_previous_translations():
    cached = CachedTranslator(FakeBackend(), 2)
    cached.translate_many(["one", "one", "two"])
    assert cached.last_hits == 0
    cached.translate_many(["one", "one", "new"])
    assert cached.last_hits == 2

def test_incomplete_backend_output_is_not_cached():
    backend = FakeBackend()
    backend.translate_many = lambda texts: []
    with pytest.raises(RuntimeError,match="incomplete"):
        CachedTranslator(backend).translate_many(["Hello"])

def test_cloud_backend_requires_explicit_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY",raising=False)
    with pytest.raises(RuntimeError,match="GROQ_API_KEY"):
        GroqTranslator(Config(backend="groq"))

def test_invalid_configuration_rejected():
    with pytest.raises(ValueError):
        Config(cpu_threads=0)
    with pytest.raises(ValueError):
        Config(capture_interval_ms=0)
    with pytest.raises(ValueError):
        Config(min_font_px=20,max_font_px=12)

def test_argos_target_word_markers_are_not_displayed_as_boxes():
    from types import SimpleNamespace
    from halo_text.translation import LocalTranslator
    translator=LocalTranslator.__new__(LocalTranslator)
    translator.tokenizer=SimpleNamespace(
        encode=lambda text,out_type:["source"],
        decode=lambda pieces:"La\u2581technologie aide user_name.")
    translator.engine=SimpleNamespace(
        translate_batch=lambda batches,**kwargs:[SimpleNamespace(hypotheses=[["target"]])])
    assert translator.translate_many(["Technology helps user_name."])==["La technologie aide user_name."]
