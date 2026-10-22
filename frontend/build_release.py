"""Build and verify a self-contained, portable Windows HALO download."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
BUILD = FRONTEND / "build"
DIST = BUILD / "dist" / "HaloText"
ZIP = FRONTEND / "downloads" / "HaloText-Windows-0.7.2.zip"


def inside(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        raise RuntimeError(f"Refusing to touch a path outside HALO: {resolved}")
    return resolved


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def manifest_group(folder: str, optional: bool = False) -> dict:
    directory = DIST / folder
    files = []
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            files.append({"name": path.relative_to(directory).as_posix(),
                          "size": path.stat().st_size, "sha256": digest(path)})
    return {"folder": folder, "optional": optional, "files": files}


def notices() -> None:
    lines = ["HALO TEXT third-party components", "",
             "HALO's own source is MIT licensed (LICENSE-MIT.txt).",
             "Bundled libraries, models, and fonts retain their respective licenses.",
             "This inventory is not a substitute for their full license texts or source distributions.", "",
             "Python package license metadata:"]
    for dist in sorted(metadata.distributions(), key=lambda d: (d.metadata.get("Name") or "").lower()):
        name = dist.metadata.get("Name") or "unknown"
        license_value = dist.metadata.get("License-Expression") or dist.metadata.get("License") or "See package metadata"
        lines.append(f"{name} {dist.version}: {license_value}")
    lines += ["", "No translation or speech model is preinstalled in this download.",
              "Font license text is supplied next to each font in assets/fonts/.",
              "Piper, if bundled for optional speech output, is GPL-3.0-or-later; see https://github.com/rhasspy/piper",
              "For upstream package source and licenses, see package metadata in _internal/ and the project setup lists."]
    (DIST / "THIRD_PARTY_NOTICES.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify_empty_models() -> None:
    unexpected = [path for path in (DIST / "models").rglob("*")
                  if path.is_file() and path.name != "README.md"]
    if unexpected:
        raise RuntimeError(f"Release unexpectedly contains a model: {unexpected[0]}")


def remove_incompatible_icu() -> None:
    """Discard a non-Qt ICU DLL accidentally collected from the build host's PATH."""
    import pefile
    qt = inside(DIST / "_internal" / "PySide6" / "Qt6Core.dll")
    bundled = inside(DIST / "_internal" / "icuuc.dll")
    if not bundled.is_file():
        return
    def symbols(path):
        pe = pefile.PE(str(path))
        try:
            return {item.name.decode("ascii") for item in pe.DIRECTORY_ENTRY_EXPORT.symbols if item.name}
        finally:
            pe.close()
    qt_image = pefile.PE(str(qt))
    try:
        required = {item.name.decode("ascii") for dll in qt_image.DIRECTORY_ENTRY_IMPORT
                    if dll.dll.lower() == b"icuuc.dll" for item in dll.imports if item.name}
    finally:
        qt_image.close()
    if required and not required.issubset(symbols(bundled)):
        system_icu = Path("C:/Windows/System32/icuuc.dll")
        if not required.issubset(symbols(system_icu)):
            raise RuntimeError("Neither bundled nor Windows ICU satisfies QtCore imports")
        bundled.unlink()
        print("Removed incompatible build-host ICU DLL; Qt will use Windows ICU.", flush=True)


def smoke_launch() -> None:
    executable = DIST / "HaloText.exe"
    sys.path.insert(0, str(ROOT / "app"))
    from halo_text.ipc import request
    pipe_name = "halo-text-" + hashlib.sha256(str(DIST).casefold().encode()).hexdigest()[:20]
    process = subprocess.Popen([str(executable)], cwd=DIST,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"HALO exited during launch (code {process.returncode})")
            status = request("status", name=pipe_name, timeout=1000)
            if status.get("running") and status.get("ready"):
                return
            time.sleep(1)
        raise RuntimeError("HALO did not report a ready background window within 45 seconds")
    finally:
        try:
            request("stop", name=pipe_name, timeout=1000)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> None:
    if sys.platform != "win32":
        raise RuntimeError("Build the Windows download on Windows")
    inside(BUILD); inside(DIST); inside(ZIP)
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
               "--windowed", "--contents-directory", "_internal", "--name", "HaloText",
               "--paths", str(ROOT / "app"), "--distpath", str(BUILD / "dist"),
               "--workpath", str(BUILD / "work"), "--specpath", str(BUILD),
               "--collect-submodules", "halo_text"]
    for module in ("rapidocr", "onnxruntime", "ctranslate2", "sentencepiece",
                   "faster_whisper", "av", "pyaudiowpatch", "edge_tts", "piper",
                   "indicnlp", "sacremoses", "langdetect", "mss", "cv2"):
        command += ["--collect-all", module]
    command += [str(FRONTEND / "portable_entry.py")]
    if "--assemble-only" not in sys.argv:
        print("Building HALO Windows application...", flush=True)
        build_env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(BUILD / "cache"),
                         TEMP=str(ROOT / "runtime" / "temp"),
                         TMP=str(ROOT / "runtime" / "temp"))
        subprocess.run(command, cwd=ROOT, check=True, env=build_env)
    elif not (DIST / "HaloText.exe").is_file():
        raise RuntimeError("No existing HALO build to assemble")
    remove_incompatible_icu()
    for package in ("rapidocr", "onnxruntime", "ctranslate2", "PySide6-Essentials"):
        dist_info = Path(metadata.distribution(package)._path)
        destination = DIST / "_internal" / dist_info.name
        if destination.exists():
            shutil.rmtree(inside(destination))
        shutil.copytree(dist_info, destination)
    for source, target in ((ROOT / "assets", DIST / "assets"),
                           (ROOT / "app", DIST / "source" / "app"),
                           (ROOT / "setup", DIST / "source" / "setup")):
        inside(target)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    models = inside(DIST / "models")
    if models.exists():
        shutil.rmtree(models)
    models.mkdir()
    (models / "README.md").write_text(
        "No models are preinstalled. Right-click H, choose an output language, then use Download offline model for selected language. "
        "The English speech model is a separate optional download.\n", encoding="utf-8")
    verify_empty_models()
    settings = inside(DIST / "settings")
    if settings.exists():
        shutil.rmtree(settings)
    settings.mkdir()
    release_config = json.loads((ROOT / "settings" / "config.json").read_text(encoding="utf-8"))
    release_config.update({"backend": "auto", "target": "hi"})
    (settings / "config.json").write_text(json.dumps(release_config, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(ROOT / "settings" / "README.md", settings / "README.md")
    shutil.copy2(ROOT / "README.md", DIST / "README.md")
    shutil.copy2(FRONTEND / "manual.html", DIST / "MANUAL.html")
    shutil.copy2(ROOT / "LICENSE", DIST / "LICENSE-MIT.txt")
    (DIST / "source" / "README.md").write_text(
        "HALO Python source under app/ and setup/ is MIT licensed. The packaged EXE uses its own bundled copy; editing these sources does not alter it.\n",
        encoding="utf-8")
    notices()
    manifest = {"schema": 1, "groups": [manifest_group("assets/fonts")]}
    (DIST / "release-integrity.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Verifying bundled assets...", flush=True)
    # Check both the command path and the actual floating background application.
    subprocess.run([str(DIST / "HaloText.exe"), "--status"], cwd=DIST, check=True, timeout=30)
    smoke_launch()
    inside(ZIP)
    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3,
                         allowZip64=True) as archive:
        for path in sorted(DIST.rglob("*")):
            if path.is_file() and not path.is_relative_to(DIST / "runtime"):
                archive.write(path, Path("HaloText") / path.relative_to(DIST))
    with zipfile.ZipFile(ZIP) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"ZIP verification failed: {bad}")
    size = ZIP.stat().st_size
    sha = digest(ZIP)
    page = FRONTEND / "index.html"
    html = page.read_text(encoding="utf-8")
    import re
    download_html = (
        '<section class="download" id="download"><h2>Get HALO for Windows</h2>'
        '<p>Portable 64-bit Windows package with no preinstalled language or speech models. '
        'Unzip to a writable folder, double-click <code>HaloText.exe</code>, then right-click H. '
        'Choose a language and download its offline model if available. See the included manual.</p>'
        '<a class="button" href="downloads/HaloText-Windows-0.7.2.zip" download>Download HALO TEXT</a>'
        f'<p class="small">Version 0.7.2 · {size / 1024**3:.2f} GB · '
        'Unsigned prototype; Windows may warn about its publisher.</p>'
        f'<p class="small">SHA-256: <code>{sha}</code></p>'
        '<p class="small">HALO source is MIT licensed. Models, fonts, and libraries retain their own licenses.</p>'
        '</section>')
    html = re.sub(r'<section class="download" id="download">.*?</section>',
                  lambda match: download_html, html, count=1, flags=re.DOTALL)
    page.write_text(html, encoding="utf-8")
    print(f"Ready: {ZIP} ({size:,} bytes) SHA-256 {sha}", flush=True)


if __name__ == "__main__":
    main()
