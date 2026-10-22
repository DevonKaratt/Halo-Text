"""Register existing Windows fonts explicitly, including in off-screen tests."""
import os
from pathlib import Path
from PySide6.QtGui import QFont, QFontDatabase, QRawFont

def load_fonts():
    directory = Path(os.environ.get("WINDIR",r"C:\Windows")) / "Fonts"
    for name in ("segoeui.ttf","segoeuib.ttf","Nirmala.ttc","Nirmala.ttf","mangal.ttf","ebrima.ttf","LeelawUI.ttf","mmrtext.ttf","malgun.ttf","YuGothR.ttc","msgothic.ttc"):
        path = directory/name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    from .paths import ROOT
    for path in (ROOT/"assets"/"fonts").glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(path))
    font = QFont("Nirmala UI")
    font.setPixelSize(24)
    raw = QRawFont.fromFont(font)
    if not raw.isValid() or not raw.supportsCharacter(0x0939):
        raise RuntimeError("A Hindi font is unavailable. Install the Windows Hindi/Nirmala UI font and retry.")
