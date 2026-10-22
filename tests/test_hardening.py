import numpy as np
from halo_text.core import Box,text_regions_differ,frame_signature,frames_differ

def test_one_small_character_change_on_4k_screen_is_not_hidden():
    original=np.full((2160,3840,3),255,np.uint8)
    changed=original.copy()
    changed[100:104,100:104]=0
    box=Box(80,80,300,40)
    assert not frames_differ(frame_signature(original),frame_signature(changed))
    assert text_regions_differ(original,changed,[box])

def test_blinking_thin_caret_does_not_invalidate_translation():
    original=np.full((100,400,3),255,np.uint8)
    changed=original.copy()
    changed[25:45,100]=0
    assert not text_regions_differ(original,changed,[Box(20,20,300,40)])

def test_changes_outside_translated_text_do_not_trigger_local_guard():
    original=np.full((100,400,3),255,np.uint8)
    changed=original.copy()
    changed[70:85,350:370]=0
    assert not text_regions_differ(original,changed,[Box(20,20,300,40)])

def test_color_only_text_change_is_detected():
    original=np.full((100,400,3),255,np.uint8)
    changed=original.copy()
    original[25:35,80:90]=(0,0,255)
    changed[25:35,80:90]=(255,0,0)
    assert text_regions_differ(original,changed,[Box(20,20,300,40)])

def test_generated_recognition_metrics_count_missed_and_extra_text():
    from halo_text.evaluation import recognition_metrics
    from halo_text.core import TextBlock
    expected=[("Hello",Box(0,0,50,20)),("World",Box(0,50,50,20))]
    observed=[TextBlock("Hello",Box(1,1,50,20),1,20),
              TextBlock("Extra",Box(200,200,50,20),1,20)]
    result=recognition_metrics(expected,observed)
    assert result["matched_lines"]==1 and result["extra_lines"]==1
    assert result["character_errors"]==10
