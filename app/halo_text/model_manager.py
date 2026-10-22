"""Inventory and safe removal of project-owned downloaded model packs."""
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from .paths import MODELS
from .languages import LANGUAGES
from .model_setup import MODEL_CODES

from .indic_setup import TARGET_TAGS
INDIC_LANGUAGES=tuple(TARGET_TAGS)

@dataclass(frozen=True)
class ModelEntry:
    key: str
    title: str
    folder: Path
    kind: str
    languages: tuple[str,...]
    size_bytes: int


def folder_bytes(folder:Path)->int:
    return sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())


def _entry(key,title,folder,kind,languages):
    return ModelEntry(key,title,folder,kind,tuple(languages),folder_bytes(folder))


def installed_models():
    """List complete, known HALO packs; no arbitrary directories are exposed."""
    entries=[]
    reverse={model_code:code for code,model_code in MODEL_CODES.items()}
    for metadata in sorted(MODELS.glob("translate-en_*/metadata.json")):
        folder=metadata.parent
        try:data=json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError,ValueError):continue
        code=reverse.get(data.get("to_code"),data.get("to_code"))
        if (folder.name!=f"translate-en_{code}" or code not in LANGUAGES
                or data.get("from_code")!="en" or not (folder/"model/model.bin").is_file()
                or not (folder/"sentencepiece.model").is_file()):
            continue
        entries.append(_entry("translation:"+code,LANGUAGES[code].name+" translation",folder,"translation",(code,)))
    from .pair_models import find as find_pair, _model_code
    for metadata in sorted(MODELS.glob("translate-*_*/metadata.json")):
        folder=metadata.parent
        if folder.name.startswith("translate-en_"):
            continue
        try:data=json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError,ValueError):continue
        name=folder.name.removeprefix("translate-")
        if "_" not in name:continue
        source,target=name.rsplit("_",1)
        if (not isinstance(source,str) or not isinstance(target,str)
                or data.get("from_code")!=_model_code(source)
                or data.get("to_code")!=_model_code(target)
                or target not in LANGUAGES or find_pair(source,target)!=folder):
            continue
        entries.append(_entry("pair:"+source+":"+target,
                              f"{source} → {LANGUAGES[target].name} translation",folder,
                              "translation",(target,)))
    from .indic_setup import DIRECTORY as indic_dir,installed as indic_installed
    if indic_installed():
        entries.append(_entry("indic","22 Indian languages (shared translation pack)",indic_dir,"translation",INDIC_LANGUAGES))
    from .speech_setup import SPEECH_MODEL as speech_dir,installed as speech_installed
    if speech_installed():
        entries.append(_entry("speech","English speech recognition",speech_dir,"audio",("en",)))
    from .voice_setup import DIRECTORY as voice_dir,installed as voice_installed
    if voice_installed():
        entries.append(_entry("voices-hi","Hindi spoken voices",voice_dir,"audio",("hi",)))
    from .ocr_packs import PACKS,folder as ocr_folder,installed as ocr_installed
    for key,(title,*_) in PACKS.items():
        if ocr_installed(key):
            entries.append(_entry("ocr:"+key,title+" OCR",ocr_folder(key),"ocr",()))
    return entries


def _check_deletion_path(folder):
    root=MODELS.resolve(strict=True)
    resolved=folder.resolve(strict=True)
    if resolved.parent!=root or folder.is_symlink() or (hasattr(os.path,"isjunction") and os.path.isjunction(folder)):
        raise RuntimeError("Model deletion target is outside HALO's models folder or is a link.")
    for child in folder.rglob("*"):
        if child.is_symlink() or (hasattr(os.path,"isjunction") and os.path.isjunction(child)):
            raise RuntimeError("Linked content found in model pack; refusing recursive removal.")
        if not child.resolve().is_relative_to(resolved):
            raise RuntimeError("Model content escapes its pack folder.")
    return resolved


def remove_model(key,active_target,audio_active=False):
    matches=[entry for entry in installed_models() if entry.key==key]
    if len(matches)!=1:
        raise RuntimeError("This installed model was not found. Refresh the controls.")
    entry=matches[0]
    if entry.kind=="translation" and active_target in entry.languages:
        raise RuntimeError("The selected output language uses this pack. Choose another language first.")
    if audio_active and entry.kind=="audio":
        raise RuntimeError("Stop audio translation before removing an audio model.")
    _check_deletion_path(entry.folder)
    shutil.rmtree(entry.folder)
    return entry
