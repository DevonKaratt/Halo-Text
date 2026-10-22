"""Run with Python 3.13. Installs everything inside this folder."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"app"))
sys.pycache_prefix = str(__import__("pathlib").Path(__file__).resolve().parents[1]/"runtime/bytecode")


def main():
    parser = argparse.ArgumentParser(description="Set up HALO TEXT locally.")
    parser.add_argument("--model-only", action="store_true")
    parser.add_argument("--with-audio",action="store_true")
    from halo_text.languages import LANGUAGES
    parser.add_argument("--target",choices=LANGUAGES,default=None)
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("The desktop application currently supports Windows only.")
    os.chdir(ROOT)
    os.environ["PYTHONPATH"]=str(ROOT/"app")
    from halo_text.paths import configure
    configure()
    from halo_text.config import load_config
    target=args.target or load_config().target
    if args.model_only:
        from halo_text.model_setup import install
        install(target)
        return
    interpreter = ROOT / ".venv" / "Scripts" / "python.exe"
    if not interpreter.exists():
        print("Creating a project-local Python environment...", flush=True)
        venv.create(ROOT / ".venv", with_pip=True)
    requirements = ROOT / "setup" / "requirements.lock.txt"
    if not requirements.exists():
        requirements = ROOT / "setup" / "requirements.txt"
    # Keep long paths inside this project; do not require a machine-wide registry change.
    install_python = "\\\\?\\" + str(interpreter.resolve())
    subprocess.check_call([install_python, "-m", "pip", "install",
                           "--disable-pip-version-check", "--timeout", "120", "--retries", "5", "-r", str(requirements)])
    subprocess.check_call([str(interpreter), "-m", "halo_text.font_setup"])
    subprocess.check_call([str(interpreter), "-m", "halo_text.model_setup", "--target", target])
    if args.with_audio:
        subprocess.check_call([str(interpreter), "-m", "halo_text.speech_setup"])
        if target == "hi":
            subprocess.check_call([str(interpreter), "-m", "halo_text.voice_setup"])
    subprocess.check_call([str(interpreter), "app/run.py", "--check", "--target", target])
    print("\nReady. Double-click Start Halo.pyw to run in the background.")

if __name__ == "__main__":
    main()
