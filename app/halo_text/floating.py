"""A draggable native HALO control icon; all saved state stays in the project."""
import json
import logging
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QRect,QRectF,QEvent,Signal,QTimer
from PySide6.QtGui import QColor,QFont,QPainter,QRegion
from PySide6.QtWidgets import QApplication,QWidget
from .paths import STATE
from .windows import exclude_from_capture

log=logging.getLogger("halo")
SIZE=68

def clamp_position(point,areas,size=SIZE):
    """Keep the complete icon in the nearest available display, including negative origins."""
    if not areas:
        return QPoint(point)
    def distance(rect):
        x=min(max(point.x()+size//2,rect.left()),rect.right())
        y=min(max(point.y()+size//2,rect.top()),rect.bottom())
        return (point.x()+size//2-x)**2+(point.y()+size//2-y)**2
    area=min(areas,key=distance)
    return QPoint(min(max(point.x(),area.left()),max(area.left(),area.right()-size+1)),
                  min(max(point.y(),area.top()),max(area.top(),area.bottom()-size+1)))

class FloatingHalo(QWidget):
    controls_requested=Signal(object)
    select_requested=Signal(object)
    exclusion_failed=Signal()

    def __init__(self,application,state_path=None):
        super().__init__()
        self.application=application
        self.state_path=Path(state_path) if state_path else STATE/"floating.json"
        self._checking=False
        self._closing=False
        self.excluded=False
        self.mode="loading"
        self._press_global=None
        self._press_position=None
        self._dragged=False
        self._screens=[]
        self.setWindowTitle("HALO TEXT floating controls")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|
                            Qt.WindowType.Tool|Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(SIZE,SIZE)
        self.setMask(QRegion(QRect(4,4,SIZE-8,SIZE-8),QRegion.RegionType.Ellipse))
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.move(self.restore_position())
        self.apply_exclusion()
        self.set_status("English","Hindi","Loading models...",False,False,False)
        application.screenAdded.connect(self.displays_changed)
        application.screenRemoved.connect(self.displays_changed)
        self.bind_displays()

    def areas(self):
        return [screen.availableGeometry() for screen in self.application.screens()]

    def restore_position(self):
        primary=self.application.primaryScreen()
        area=primary.availableGeometry() if primary else QRect(0,0,800,600)
        default=QPoint(area.right()-SIZE-20,area.bottom()-SIZE-100)
        try:
            data=json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(data,dict):
                raise ValueError("Invalid saved position")
            if type(data.get("x")) is int and type(data.get("y")) is int:
                default=QPoint(data["x"],data["y"])
        except (OSError,ValueError,TypeError):
            pass
        return clamp_position(default,self.areas())

    def save_position(self):
        try:
            self.state_path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.state_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"x":self.x(),"y":self.y()},indent=2),encoding="utf-8")
            temporary.replace(self.state_path)
        except OSError:
            log.warning("Floating icon position could not be saved.")

    def bind_displays(self):
        current=self.application.screens()
        self._screens=[s for s in self._screens if any(s is live for live in current)]
        for screen in current:
            if not any(screen is old for old in self._screens):
                screen.availableGeometryChanged.connect(self.ensure_on_screen)
                self._screens.append(screen)

    def displays_changed(self,*args):
        self.bind_displays()
        QTimer.singleShot(0,self.ensure_on_screen)

    def ensure_on_screen(self,*args):
        if self._closing:
            return
        position=clamp_position(self.pos(),self.areas())
        if position!=self.pos():
            self.move(position)
            self.save_position()

    def apply_exclusion(self):
        if self._checking or self._closing:
            return self.excluded
        self._checking=True
        try:
            self.excluded=exclude_from_capture(self.winId())
        finally:
            self._checking=False
        if not self.excluded:
            self.hide()
        return self.excluded

    def event(self,event):
        result=super().event(event)
        if event.type()==QEvent.Type.WinIdChange and hasattr(self,"_checking") and not self._checking:
            if not self.apply_exclusion() and not self._closing:
                self.exclusion_failed.emit()
        return result

    def showEvent(self,event):
        super().showEvent(event)
        if not self.apply_exclusion():
            self.hide()
            self.exclusion_failed.emit()

    def set_status(self,source,target,message,ready,busy,watching):
        self.mode="loading" if not ready else "busy" if busy else "watching" if watching else "ready"
        self.setToolTip(f"HALO TEXT | {source} > {target}\n{message}\nDrag to move | Right-click controls | Double-click select")
        self.update()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self._press_global=event.globalPosition().toPoint()
            self._press_position=self.pos()
            self._dragged=False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self._press_global is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta=event.globalPosition().toPoint()-self._press_global
            if self._dragged or delta.manhattanLength()>=QApplication.startDragDistance():
                self._dragged=True
                self.move(clamp_position(self._press_position+delta,self.areas()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self._press_global is not None:
            if self._dragged:
                self.save_position()
            self._press_global=self._press_position=None
            self._dragged=False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self._press_global=self._press_position=None
            self.select_requested.emit(self.screen())
            event.accept()

    def contextMenuEvent(self,event):
        self._press_global=self._press_position=None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.controls_requested.emit(event.globalPos())
        event.accept()

    def closeEvent(self,event):
        self.save_position()
        self._closing=True
        super().closeEvent(event)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2563eb"))
        p.drawEllipse(QRectF(5,5,58,58))
        font=QFont("Segoe UI")
        font.setPixelSize(28)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("white"))
        p.drawText(QRectF(5,5,58,58),Qt.AlignmentFlag.AlignCenter,"H")
        p.end()
