from dataclasses import dataclass
import numpy as np
import mss
from .core import Box

@dataclass(frozen=True)
class ScreenMapping:
    left: int
    top: int
    width: int
    height: int
    logical_width: int
    logical_height: int

    @property
    def sx(self): return self.width / self.logical_width

    @property
    def sy(self): return self.height / self.logical_height

    def to_physical(self, rect):
        x, y, width, height = rect
        return Box(round(x*self.sx), round(y*self.sy),
                   round(width*self.sx), round(height*self.sy)).clip(self.width, self.height)

def mapping_for_screen(screen, monitors):
    """Match device identity, never monitor ordering or scaled desktop positions."""
    matches = [m for m in monitors if m["name"].casefold() == screen.name().casefold()]
    if not matches and len(monitors) == 1:
        matches = monitors
    if len(matches) != 1:
        raise RuntimeError("Cannot map the selected display to Windows capture coordinates.")
    monitor = matches[0]
    geometry = screen.geometry()
    return ScreenMapping(monitor["left"],monitor["top"],monitor["width"],monitor["height"],
                         geometry.width(),geometry.height())

class ScreenCapture:
    def __init__(self, screen):
        from .windows import enumerate_monitors
        self.mapping = mapping_for_screen(screen, enumerate_monitors())
        self.sct = mss.mss()

    def grab(self, region):
        m = self.mapping
        if region.w <= 0 or region.h <= 0 or region != region.clip(m.width,m.height):
            raise ValueError("The capture region is outside the selected display.")
        image = self.sct.grab({"left": m.left + region.x, "top": m.top + region.y,
                               "width": region.w, "height": region.h})
        return np.asarray(image)[:, :, :3].copy()

    def close(self):
        self.sct.close()
