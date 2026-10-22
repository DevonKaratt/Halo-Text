"""All application-owned files stay under the project directory."""
import os
import sys
from pathlib import Path

ROOT = Path(sys.executable).resolve().parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"
STATE = ROOT / "runtime/state"

def configure():
    sys.pycache_prefix = str(ROOT / "runtime" / "bytecode")
    for name in ("runtime/cache", "runtime/temp", "runtime/state", "runtime/bytecode", "models", "reports", "settings"):
        (ROOT / name).mkdir(parents=True,exist_ok=True)
    for key, value in {
        "TEMP": ROOT / "runtime/temp", "TMP": ROOT / "runtime/temp",
        "PIP_CACHE_DIR": ROOT / "runtime/cache" / "pip",
        "HF_HOME": ROOT / "runtime/cache" / "huggingface",
        "XDG_CACHE_HOME": ROOT / "runtime/cache",
        "MPLCONFIGDIR": ROOT / "runtime/cache" / "matplotlib",
        "PYTHONPYCACHEPREFIX": ROOT / "runtime" / "bytecode",
        "QT_LOGGING_RULES": "qt.qpa.window=false",
    }.items():
        os.environ[key] = str(value)
