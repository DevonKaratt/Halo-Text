import pytest
from halo_text.config import Config

def test_fast_captions_shortens_waits_and_preserves_document_configuration():
    normal=Config()
    fast=Config(fast_captions=True)
    assert normal.watch_timing()==(350,700,1800)
    assert fast.watch_timing()==(50,0,100)
    assert fast.settle_ms==normal.settle_ms

def test_custom_document_timings_remain_effective():
    assert Config(capture_interval_ms=400,settle_ms=900,auto_interval_ms=2000).watch_timing()==(400,900,2000)

def test_caption_setting_rejects_non_boolean():
    with pytest.raises(ValueError):
        Config(fast_captions="true")
