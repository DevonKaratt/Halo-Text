"""Install a supported free Argos translation model inside the project."""
import argparse
import hashlib
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path
from .paths import MODELS, ROOT, configure
from .languages import LANGUAGES, language

MODEL_CODES={"zh-CN":"zh","fil":"tl"}

INDEX = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"

def read_index():
    """Read the public model catalogue without depending on GitHub API quota."""
    mirrors=(INDEX,"https://cdn.jsdelivr.net/gh/argosopentech/argospm-index@main/index.json")
    last_error=None
    for url in mirrors:
        try:
            request=urllib.request.Request(url,headers={"User-Agent":"HALO-TEXT"})
            with urllib.request.urlopen(request,timeout=20) as response:
                entries=json.load(response)
            if not isinstance(entries,list):
                raise ValueError("Invalid model catalogue")
            return entries
        except (OSError,ValueError) as exc:
            last_error=exc
    raise RuntimeError("Could not reach the public offline model catalogue. Check the connection and retry.") from last_error

def find_model(target="hi"):
    language(target)
    for metadata in sorted(MODELS.glob("*/metadata.json")):
        try:
            data = json.loads(metadata.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        base = metadata.parent
        if (data.get("from_code") == "en" and data.get("to_code") == MODEL_CODES.get(target,target)
                and (base / "model" / "model.bin").is_file()
                and (base / "sentencepiece.model").is_file()):
            return base
    return None

def installed_languages():
    from .online import route
    from .config import Config
    return [{"code":code,"name":item.name,"group":item.group,
             "installed":route(Config(target=code,backend="local")) in {"local","indic"},
             "provider":route(Config(target=code,backend="auto"))}
            for code,item in LANGUAGES.items()]

def extract_package(archive, staging, target):
    """Validate all archive paths and language metadata before installing."""
    language(target)
    staging.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            path = (staging / info.filename).resolve()
            if (not path.is_relative_to(staging.resolve())
                    or (info.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Unsafe path in model archive")
        zf.extractall(staging)
    sources = list(staging.glob("**/metadata.json"))
    for metadata in sources:
        data = json.loads(metadata.read_text(encoding="utf-8"))
        source = metadata.parent
        if data.get("from_code") == "en" and data.get("to_code") == MODEL_CODES.get(target,target):
            if ((source/"sentencepiece.model").is_file()
                    and (source/"model"/"model.bin").is_file()):
                return source
    raise RuntimeError("Archive does not contain the expected complete English-to-" + target + " model.")

def install(target="hi"):
    configure()
    name = language(target).name
    from .indic_setup import TARGET_TAGS, install as install_indic
    if target in TARGET_TAGS:
        return install_indic()
    existing = find_model(target)
    if existing:
        print(f"English-to-{name} model ready: {existing}", flush=True)
        return existing
    print("Reading the official Argos model index...", flush=True)
    entries=read_index()
    candidates = [p for p in entries if p.get("from_code") == "en" and p.get("to_code") == MODEL_CODES.get(target,target)]
    if not candidates:
        raise RuntimeError(f"No English-to-{name} model in the public Argos index.")
    package = candidates[-1]
    url = next(u for u in package["links"] if u.startswith("https://"))
    archive = ROOT/"runtime/cache"/("english-hindi.argosmodel" if target=="hi" else f"translate-en_{target}.argosmodel")
    partial = archive.with_suffix(".part")
    if not archive.is_file():
        print(f"Downloading translation weights from {url}", flush=True)
        request = urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(request,timeout=120) as response, partial.open("wb") as out:
            total = int(response.headers.get("Content-Length",0))
            count,last = 0,-1
            while chunk := response.read(1024*1024):
                out.write(chunk)
                count += len(chunk)
                progress = count // (20*1024*1024)
                if progress != last:
                    print(f"Downloaded {count//(1024*1024)} MB" +
                          (f" / {total//(1024*1024)} MB" if total else ""),flush=True)
                    last=progress
            if total and count != total:
                raise RuntimeError("Incomplete model download; rerun installation.")
        partial.replace(archive)
    # Unique staging prevents a partial old extraction from passing validation.
    import tempfile
    with tempfile.TemporaryDirectory(prefix=f"model-{target}-",dir=ROOT/"runtime/temp") as temporary:
        staging=Path(temporary)
        source=extract_package(archive,staging,target)
        destination=MODELS/f"translate-en_{target}"
        if destination.exists():
            raise RuntimeError(f"An incomplete model exists at {destination}; inspect it before retrying.")
        shutil.move(str(source),str(destination))
    with archive.open("rb") as stream:
        archive_hash=hashlib.file_digest(stream,"sha256").hexdigest()
    manifest={"index":INDEX,"url":url,"package":package,"archive_sha256":archive_hash}
    (destination/"source.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    stanza=(destination/"stanza").resolve()
    if not stanza.is_relative_to(MODELS.resolve()):
        raise RuntimeError("Unsafe tokenizer cleanup path")
    if stanza.is_dir():
        shutil.rmtree(stanza)  # This runtime uses SentencePiece directly.
    archive.unlink(missing_ok=True)  # Keep installed weights and provenance, not a duplicate archive.
    print(f"Installed: {destination}",flush=True)
    return destination

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--target",choices=LANGUAGES,default="hi")
    install(parser.parse_args().target)
