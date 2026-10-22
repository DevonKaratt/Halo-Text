from halo_text.core import Box, TextBlock, Translation
from halo_text.config import Config

def test_hindi_is_shaped_and_fits_without_clipping(qapp):
    from halo_text.overlay import prepare_paint_blocks
    from PySide6.QtGui import QImage,QPainter,QColor
    from halo_text.overlay import paint_blocks
    translation = Translation(TextBlock("Welcome",Box(30,30,400,44),0.99,40), "आपका स्वागत है")
    items, skipped = prepare_paint_blocks([translation],Config())
    assert len(items) == 1 and skipped == 0
    layout = items[0].layout
    assert layout.lineCount() >= 1
    assert layout.boundingRect().height() <= items[0].rect.height()
    image = QImage(500,120,QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    paint_blocks(painter,items)
    painter.end()
    assert any(image.pixelColor(x, y).lightness() < 180
               for x in range(30,400,3) for y in range(30,74,3))

def test_unfittable_translation_leaves_original_uncovered(qapp):
    from halo_text.overlay import prepare_paint_blocks
    translation = Translation(TextBlock("OK",Box(0,0,15,10),0.9,10),
                              "यह अनुवाद इस छोटे स्थान में बिल्कुल नहीं समा सकता")
    items, skipped = prepare_paint_blocks([translation],Config())
    assert not items
    assert skipped == 1

def test_scaled_overlay_uses_region_offset(qapp):
    from halo_text.overlay import prepare_paint_blocks
    translation = Translation(TextBlock("Hello",Box(20,30,500,60),1,50),"नमस्ते")
    items,_ = prepare_paint_blocks([translation],Config(),sx=1.5,sy=1.5,offset=(100,150))
    assert items[0].rect.x() == 78
    assert items[0].rect.y() == 118

def test_caption_uses_selected_strip_when_translation_exceeds_source_box(qapp):
    from PySide6.QtCore import QRectF
    from halo_text.overlay import prepare_paint_blocks,prepare_region_caption
    translation=Translation(TextBlock("Hello",Box(20,20,60,16),.99,16),
        "எங்கள் திட்டத்திற்கு வரவேற்கிறோம். இது ஒரு மொழிபெயர்ப்பு சோதனை.")
    config=Config(target="ta",fast_captions=True)
    original,skipped=prepare_paint_blocks([translation],config)
    assert not original and skipped==1
    items,skipped=prepare_region_caption([translation],config,QRectF(0,0,900,110))
    assert len(items)==1 and skipped==0
    assert items[0].layout.text()==translation.text
    assert items[0].layout.boundingRect().height()<=items[0].rect.height()


def test_font_contains_actual_devanagari_glyphs(qapp):
    from PySide6.QtGui import QFont,QRawFont
    font=QFont("Nirmala UI")
    font.setPixelSize(24)
    raw=QRawFont.fromFont(font)
    assert raw.isValid()
    assert all(raw.supportsCharacter(ord(ch)) for ch in "हिन्दीस्वागत")
