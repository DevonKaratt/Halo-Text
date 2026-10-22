"""Direct source-to-target Argos packs for optional offline multilingual input."""
import hashlib
import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from .paths import MODELS, ROOT, configure
from .languages import LANGUAGES
from .model_setup import MODEL_CODES


def _model_code(code):
    return MODEL_CODES.get(code,code)


def _code(code):
    if not code or not code.replace("-", "").isalnum() or len(code) > 12:
        raise ValueError("Invalid language code")
    return code


def folder(source, target):
    return MODELS / f"translate-{_code(source)}_{_code(target)}"


def find(source, target):
    base = folder(source, target)
    metadata = base / "metadata.json"
    try:
        data = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (data.get("from_code") == _model_code(source) and data.get("to_code") == _model_code(target)
            and (base / "model/model.bin").is_file()
            and (base / "sentencepiece.model").is_file()):
        return base
    return None


def _index():
    from .model_setup import read_index
    return read_index()


def install(source, target):
    configure()
    _code(source); _code(target)
    if target not in LANGUAGES or source == target:
        raise ValueError("Unsupported translation pair")
    existing = find(source, target)
    if existing:
        return existing
    candidates = [item for item in _index()
                  if item.get("from_code") == _model_code(source) and item.get("to_code") == _model_code(target)]
    if not candidates:
        raise RuntimeError(f"No direct offline Argos model for {source} to {target}; use online translation.")
    package = candidates[-1]
    url = next((link for link in package.get("links", []) if link.startswith("https://")), None)
    if not url:
        raise RuntimeError("Offline pack has no HTTPS download")
    destination = folder(source, target)
    if destination.exists():
        raise RuntimeError("Incomplete offline pack exists; remove it before retrying")
    with tempfile.TemporaryDirectory(prefix="halo-pair-", dir=ROOT / "runtime/temp") as temporary:
        staging = Path(temporary)
        archive = staging / "model.argosmodel"
        request = urllib.request.Request(url, headers={"User-Agent": "HALO-TEXT"})
        with urllib.request.urlopen(request, timeout=120) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
        extracted = staging / "extracted"
        extracted.mkdir()
        with zipfile.ZipFile(archive) as zf:
            for item in zf.infolist():
                path = (extracted / item.filename).resolve()
                if (not path.is_relative_to(extracted.resolve())
                        or (item.external_attr >> 16) & 0o170000 == 0o120000):
                    raise RuntimeError("Unsafe path in translation pack")
            zf.extractall(extracted)
        matches = []
        for metadata in extracted.glob("**/metadata.json"):
            data = json.loads(metadata.read_text(encoding="utf-8"))
            base = metadata.parent
            if (data.get("from_code") == _model_code(source) and data.get("to_code") == _model_code(target)
                    and (base / "model/model.bin").is_file()
                    and (base / "sentencepiece.model").is_file()):
                matches.append(base)
        if len(matches) != 1:
            raise RuntimeError("Downloaded archive lacks the expected translation pair")
        shutil.move(str(matches[0]), str(destination))
    stanza=destination/"stanza"
    if stanza.is_dir() and not stanza.is_symlink():
        shutil.rmtree(stanza)  # HALO uses SentencePiece directly.
    (destination / "source.json").write_text(
        json.dumps({"url": url, "archive_sha256": archive_hash}, indent=2), encoding="utf-8")
    return destination
