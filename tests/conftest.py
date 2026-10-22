import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"app"))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["TEMP"] = str(ROOT/"runtime/temp")
os.environ["TMP"] = str(ROOT/"runtime/temp")
(ROOT/"runtime/temp").mkdir(parents=True,exist_ok=True)
from halo_text.paths import configure
configure()
import pytest

@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from halo_text.fonts import load_fonts
    load_fonts()
    return app
