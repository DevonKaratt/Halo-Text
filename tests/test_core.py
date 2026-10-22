import numpy as np
from halo_text.core import Box, TextBlock, TranslationCache, group_lines, frames_differ, frame_signature, is_english_candidate
from halo_text.capture import ScreenMapping

def line(text,x,y,w=200,h=20):
    return TextBlock(text,Box(x,y,w,h),0.95,h)

def test_paragraphs_join_but_columns_and_headings_stay_separate():
    blocks = group_lines([line("Heading",10,10,300,35),
                          line("First line",10,60), line("Other column",400,60),
                          line("Second line",10,88), line("Other paragraph",400,150)])
    assert [b.text for b in blocks] == ["Heading","First line Second line","Other column","Other paragraph"]
    assert blocks[1].box == Box(10,60,200,48)

def test_small_local_text_change_is_detected_on_large_screen():
    a = np.full((1080,1920,3),255,np.uint8)
    b = a.copy()
    b[300:320,600:640] = 0
    assert frames_differ(frame_signature(a),frame_signature(b))

def test_minor_noise_does_not_force_retranslation():
    a = np.full((600,1000,3),200,np.uint8)
    b = a.copy()
    b[::10,::10] += 2
    assert not frames_differ(frame_signature(a),frame_signature(b))

def test_changed_frame_shape_is_never_accepted():
    assert frames_differ(np.zeros((50,50),np.uint8),np.zeros((60,50),np.uint8))

def test_text_change_at_partial_edge_tile_is_detected():
    first = np.full((100, 100), 255, np.uint8)
    second = first.copy()
    second[96:100, 96:100] = 0
    assert frames_differ(first, second)

def test_screen_scaling_maps_selection_to_capture_pixels():
    mapping = ScreenMapping(0,0,1920,1080,1280,720)
    assert mapping.to_physical((100,100,400,200)) == Box(150,150,600,300)
    assert mapping.to_physical((-10,0,100,100)) == Box(0,0,135,150)

def test_cache_normalizes_whitespace_and_evicts_least_recent():
    cache = TranslationCache(2)
    cache.put("Hello world","नमस्ते दुनिया")
    cache.put("Good morning","सुप्रभात")
    assert cache.get("Hello   world") == "नमस्ते दुनिया"
    cache.put("Thank you","धन्यवाद")
    assert cache.get("Good morning") is None

def test_only_likely_english_text_enters_pipeline():
    assert is_english_candidate("Save your work.")
    assert not is_english_candidate("2026 / 10 / 16")
    assert not is_english_candidate("https://example.com")
    assert not is_english_candidate("person@example.com")
    assert not is_english_candidate("नमस्ते दुनिया")
