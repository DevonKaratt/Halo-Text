from dataclasses import dataclass
from PySide6.QtCore import Qt, QRect, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QTextLayout, QTextOption
from PySide6.QtWidgets import QWidget
from .windows import exclude_from_capture
from .languages import language

@dataclass
class PaintBlock:
    rect: QRectF
    layout: QTextLayout
    background: QColor
    foreground: QColor

def make_layout(text, width, font, rtl=False):
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    option.setTextDirection(Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight)
    option.setAlignment(Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft)
    layout.setTextOption(option)
    layout.beginLayout()
    height, widest = 0.0, 0.0
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(1.0, width))
        line.setPosition(QPointF(0, height))
        height += line.height()
        widest = max(widest, line.naturalTextWidth())
    layout.endLayout()
    return layout, height, widest

def prepare_paint_blocks(translations, config, sx=1.0, sy=1.0, offset=(0,0)):
    items, skipped = [], 0
    for item in translations:
        box = item.block.box
        # Coordinates are local to the primary monitor, not the virtual desktop.
        rect = QRectF((box.x+offset[0])/sx - 2, (box.y+offset[1])/sy - 2,
                      box.w/sx + 4, box.h/sy + 4)
        max_size = max(config.min_font_px, min(config.max_font_px,
                                              round(item.block.line_height / sy * 0.92)))
        fitted = None
        for size in range(max_size, config.min_font_px-1, -1):
            font = QFont(language(config.target).font)
            font.setPixelSize(size)
            layout, height, width = make_layout(item.text, rect.width()-4, font, language(config.target).rtl)
            if height <= rect.height()-2 and width <= rect.width()-3:
                fitted = layout
                break
        if fitted is None:
            skipped += 1
            continue
        color = QColor(*item.block.background)
        light = (0.2126*color.red() + 0.7152*color.green() + 0.0722*color.blue()) > 140
        items.append(PaintBlock(rect, fitted, color, QColor("#111827" if light else "#f8fafc")))
    return items, skipped

def paint_blocks(painter, items):
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    for item in items:
        painter.fillRect(item.rect, item.background)
        painter.setPen(item.foreground)
        painter.save()
        painter.setClipRect(item.rect)
        item.layout.draw(painter, QPointF(item.rect.x()+2, item.rect.y()+1))
        painter.restore()

def prepare_region_caption(translations, config, bounds):
    """Fit captions to the user's selection, rather than the shorter source glyph box."""
    text = " ".join(item.text.strip() for item in translations if item.text.strip())
    if not text or bounds.width() < 12 or bounds.height() < 12:
        return [], len(translations)
    rect = bounds.adjusted(2, 2, -2, -2)
    target = language(config.target)
    # Translations commonly need more lines than the source, especially Indic
    # scripts. The whole selected strip is available for those extra lines.
    for size in range(config.max_font_px, 7, -1):
        font = QFont(target.font)
        font.setPixelSize(size)
        layout, height, width = make_layout(text, rect.width()-8, font, target.rtl)
        if height <= rect.height()-4 and width <= rect.width()-8:
            rect.setTop(rect.top() + max(0, (rect.height()-height-4)/2))
            rect.setHeight(height+4)
            return [PaintBlock(rect, layout, QColor(12,18,30,245), QColor("#f8fafc"))], 0
    return [], len(translations)

class Overlay(QWidget):
    def __init__(self, screen, config):
        super().__init__()
        self.config = config
        self.items = []
        self.original_visible = False
        self.setWindowTitle("HALO TEXT translation overlay")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                            | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        # Create the native handle before applying the Windows capture exclusion.
        self.excluded = exclude_from_capture(self.winId())

    def show_translations(self, translations, mapping, region):
        self.items, skipped = prepare_paint_blocks(
            translations, self.config, mapping.sx, mapping.sy, (region.x,region.y))
        if translations and (self.config.fast_captions or not self.items):
            bounds=QRectF(region.x/mapping.sx, region.y/mapping.sy,
                          region.w/mapping.sx, region.h/mapping.sy)
            self.items, skipped = prepare_region_caption(translations, self.config, bounds)
        if self.items and not self.original_visible:
            self.show()
            self.update()
        else:
            self.hide()
        return len(self.items), skipped

    def set_original_visible(self, visible):
        self.original_visible = bool(visible)
        if self.original_visible or not self.items:
            self.hide()
        else:
            self.show()
            self.update()

    def clear(self):
        self.items = []
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        paint_blocks(painter, self.items)
        painter.end()

class RegionSelector(QWidget):
    selected = Signal(object)
    cancelled = Signal()

    def __init__(self, screen):
        super().__init__()
        self.start = None
        self.selection = QRect()
        self.done = False
        self.setWindowTitle("Choose translation area")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(9,16,29,115))
        if not self.selection.isNull():
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(self.selection, QColor(0,0,0,0))
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            p.setPen(QColor("#60a5fa"))
            p.drawRect(self.selection)
        p.fillRect(QRect(18,18,590,48), QColor("#111827"))
        p.setPen(QColor("#ffffff"))
        p.setFont(QFont("Segoe UI", 11))
        p.drawText(QRect(32,18,566,48), Qt.AlignmentFlag.AlignVCenter,
                   "Drag around English text. Release to translate. Esc to cancel.")
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start = event.position().toPoint()
            self.selection = QRect(self.start,self.start)

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.selection = QRect(self.start,event.position().toPoint()).normalized().intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.start is None:
            return
        self.selection = QRect(self.start,event.position().toPoint()).normalized().intersected(self.rect())
        if self.selection.width() >= 60 and self.selection.height() >= 30:
            self.done = True
            self.hide()
            self.selected.emit(self.selection)
        else:
            self.cancel()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()

    def cancel(self):
        self.done = True
        self.hide()
        self.cancelled.emit()

    def closeEvent(self, event):
        if not self.done:
            self.cancelled.emit()
        event.accept()
