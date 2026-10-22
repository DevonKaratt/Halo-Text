"""Native click-through subtitle strip, with no recording history."""
from PySide6.QtCore import Qt,QRectF,QPointF,QTimer
from PySide6.QtGui import QColor,QFont,QPainter
from PySide6.QtWidgets import QWidget
from .overlay import make_layout
from .windows import exclude_from_capture
from .languages import language

class SubtitleOverlay(QWidget):
    def __init__(self,screen,target):
        super().__init__()
        self.target=target
        self.source=""
        self.translated=""
        self.status_text="Audio subtitles"
        self.speaker_label=""
        self.setWindowTitle("HALO TEXT audio subtitles")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|
                            Qt.WindowType.Tool|Qt.WindowType.WindowTransparentForInput|
                            Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setScreen(screen)
        geometry=screen.availableGeometry()
        width=min(1100,round(geometry.width()*.84))
        self.setGeometry(geometry.x()+(geometry.width()-width)//2,geometry.bottom()-185,width,165)
        self.excluded=exclude_from_capture(self.winId())
        self.expiry=QTimer(self)
        self.expiry.setSingleShot(True)
        self.expiry.timeout.connect(self.expire)

    def set_status(self,text):
        self.status_text=text
        self.show()
        self.update()

    def set_subtitle(self,source,translated,speaker_label=""):
        self.source,self.translated=source,translated
        self.speaker_label=speaker_label
        self.expiry.start(9000)
        self.show()
        self.update()

    def expire(self):
        self.source=self.translated=""
        self.speaker_label=""
        self.update()

    def clear(self):
        self.expiry.stop()
        self.source=self.translated=""
        self.speaker_label=""
        self.hide()

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(12,18,30,235))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(),12,12)
        font=QFont("Segoe UI")
        font.setPixelSize(12)
        p.setFont(font)
        p.setPen(QColor("#93c5fd"))
        p.drawText(QRectF(18,10,self.width()-36,20),Qt.AlignmentFlag.AlignLeft,
                   (self.speaker_label+" | " if self.speaker_label else "")+self.status_text+" | Ctrl+Alt+S stops")
        # Fit translations into the subtitle area; preserve source text separately.
        target_font=QFont(language(self.target).font)
        layout=None
        for size in range(25,13,-1):
            target_font.setPixelSize(size)
            layout,height,_=make_layout(self.translated,self.width()-36,target_font,language(self.target).rtl)
            if height<=88:
                break
        p.setPen(QColor("white"))
        p.save()
        p.setClipRect(QRectF(18,34,self.width()-36,88))
        if layout:
            layout.draw(p,QPointF(18,34))
        p.restore()
        font.setPixelSize(14)
        p.setFont(font)
        p.setPen(QColor("#cbd5e1"))
        p.drawText(QRectF(18,128,self.width()-36,28),Qt.AlignmentFlag.AlignLeft,
                   p.fontMetrics().elidedText(self.source,Qt.TextElideMode.ElideRight,self.width()-36))
        p.end()
