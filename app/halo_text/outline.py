"""Persistent, click-through outline for the watched screen region."""
from PySide6.QtCore import Qt,QRectF
from PySide6.QtGui import QColor,QFont,QPainter,QPen
from PySide6.QtWidgets import QWidget
from .windows import exclude_from_capture

class SelectionOutline(QWidget):
    def __init__(self,screen):
        super().__init__()
        self.area=None
        self.watching=False
        self.setWindowTitle("HALO TEXT watched area")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|
                            Qt.WindowType.Tool|Qt.WindowType.WindowTransparentForInput|
                            Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.excluded=exclude_from_capture(self.winId())

    def set_region(self,mapping,region,watching):
        self.area=QRectF(region.x/mapping.sx,region.y/mapping.sy,
                         region.w/mapping.sx,region.h/mapping.sy)
        self.watching=watching
        self.show()
        self.update()

    def set_watching(self,watching):
        self.watching=watching
        self.update()

    def clear(self):
        self.area=None
        self.hide()

    def paintEvent(self,event):
        if self.area is None:
            return
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color=QColor("#22c55e" if self.watching else "#f59e0b")
        p.setPen(QPen(color,2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(self.area.adjusted(1,1,-1,-1))
        font=QFont("Segoe UI")
        font.setPixelSize(12)
        p.setFont(font)
        label="Watching English | Ctrl+Alt+A pause | Ctrl+Alt+C clear" if self.watching else "Paused | Ctrl+Alt+A resume | Ctrl+Alt+C clear"
        width=min(self.width()-4,p.fontMetrics().horizontalAdvance(label)+16)
        if self.area.y()>=24:
            y=self.area.y()-24
        elif self.area.bottom()+26<self.height():
            y=self.area.bottom()+2
        else:
            p.end()
            return  # A full-screen outline must not cover the text with a label.
        rect=QRectF(min(self.area.x(),self.width()-width-2),y,width,22)
        p.fillRect(rect,QColor("#111827"))
        p.setPen(color)
        p.drawText(rect.adjusted(6,0,-4,0),Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(label,Qt.TextElideMode.ElideRight,round(width)-10))
        p.end()
