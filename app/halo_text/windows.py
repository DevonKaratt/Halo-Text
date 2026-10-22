"""Small Windows API bridge; no administrator privileges or keyboard hooks."""
import ctypes
from ctypes import wintypes
import sys

def require_windows():
    if sys.platform != "win32":
        raise RuntimeError("HALO TEXT currently supports Windows only.")
    if sys.getwindowsversion().build < 19041:
        raise RuntimeError("Use Windows 10 version 2004 or newer (or Windows 11).")

def enable_dpi_awareness():
    if sys.platform == "win32":
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

def exclude_from_capture(hwnd):
    fn = ctypes.windll.user32.SetWindowDisplayAffinity
    fn.argtypes = [wintypes.HWND, wintypes.DWORD]
    fn.restype = wintypes.BOOL
    return bool(fn(int(hwnd), 0x11))  # WDA_EXCLUDEFROMCAPTURE

def desktop_available():
    user = ctypes.windll.user32
    user.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user.OpenInputDesktop.restype = wintypes.HANDLE
    user.CloseDesktop.argtypes = [wintypes.HANDLE]
    handle = user.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
    if not handle:
        return False
    user.CloseDesktop(handle)
    return True

def hotkey_filter(callback):
    from PySide6.QtCore import QAbstractNativeEventFilter
    user = ctypes.windll.user32
    user.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]

    class Hotkeys(QAbstractNativeEventFilter):
        bindings = {1: "translate", 2: "region", 3: "auto", 4: "clear", 5: "quit", 6: "screen", 7: "original", 8: "audio"}
        keys = {1: "T", 2: "R", 3: "A", 4: "C", 5: "Q", 6: "F", 7: "O", 8: "S"}

        def __init__(self):
            super().__init__()
            self.registered = []
            self.failures = []
            for ident, key in self.keys.items():
                if user.RegisterHotKey(None, ident, 0x4000 | 0x0002 | 0x0001, ord(key)):
                    self.registered.append(ident)
                else:
                    self.failures.append("Ctrl+Alt+" + key)

        def nativeEventFilter(self, event_type, message):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam in self.bindings:
                callback(self.bindings[msg.wParam])
                return True, 0
            return False, 0

        def close(self):
            for ident in self.registered:
                user.UnregisterHotKey(None, ident)
            self.registered.clear()

    return Hotkeys()

def enumerate_monitors():
    """Physical desktop rectangles and stable Windows device names."""
    user=ctypes.windll.user32
    class MonitorInfo(ctypes.Structure):
        _fields_=[("cbSize",wintypes.DWORD),("rcMonitor",wintypes.RECT),
                  ("rcWork",wintypes.RECT),("dwFlags",wintypes.DWORD),
                  ("szDevice",wintypes.WCHAR*32)]
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HANDLE,wintypes.HDC,
                                     ctypes.POINTER(wintypes.RECT),wintypes.LPARAM)
    user.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.POINTER(MonitorInfo)]
    user.GetMonitorInfoW.restype=wintypes.BOOL
    user.EnumDisplayMonitors.argtypes=[wintypes.HDC,ctypes.POINTER(wintypes.RECT),
                                      callback_type,wintypes.LPARAM]
    user.EnumDisplayMonitors.restype=wintypes.BOOL
    monitors=[]
    def visit(handle,dc,rect,data):
        info=MonitorInfo()
        info.cbSize=ctypes.sizeof(info)
        if user.GetMonitorInfoW(handle,ctypes.byref(info)):
            r=info.rcMonitor
            monitors.append({"name":info.szDevice,"left":r.left,"top":r.top,
                             "width":r.right-r.left,"height":r.bottom-r.top})
        return True
    if not user.EnumDisplayMonitors(None,None,callback_type(visit),0) or not monitors:
        raise RuntimeError("No capture displays are available.")
    return monitors


def window_at(left, top, width, height):
    """Return a visible foreign top-level window beneath a selected region."""
    import os
    user=ctypes.windll.user32
    point=wintypes.POINT(left+width//2,top+height//2)
    user.WindowFromPoint.argtypes=[wintypes.POINT]
    user.WindowFromPoint.restype=wintypes.HWND
    user.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]
    user.GetAncestor.restype=wintypes.HWND
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype=wintypes.DWORD
    user.IsWindowVisible.argtypes=[wintypes.HWND]
    hwnd=user.GetAncestor(user.WindowFromPoint(point),2)  # GA_ROOT
    if not hwnd or not user.IsWindowVisible(hwnd):return None
    pid=wintypes.DWORD()
    user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    if pid.value==os.getpid():return None
    return int(hwnd) if window_rect(int(hwnd)) else None


def window_rect(hwnd):
    user=ctypes.windll.user32
    user.IsWindow.argtypes=[wintypes.HWND]
    user.IsIconic.argtypes=[wintypes.HWND]
    user.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    if not user.IsWindow(hwnd) or user.IsIconic(hwnd):return None
    rect=wintypes.RECT()
    if not user.GetWindowRect(hwnd,ctypes.byref(rect)):return None
    result=(rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top)
    return result if result[2]>=100 and result[3]>=60 else None
