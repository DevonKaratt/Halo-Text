"""Check bundled data for accidental corruption before portable HALO starts."""
import hashlib
import json
from pathlib import Path
from .paths import ROOT


def verify_release():
    manifest=ROOT/"release-integrity.json"
    if not manifest.is_file():
        return
    data=json.loads(manifest.read_text(encoding="utf-8"))
    root=ROOT.resolve()
    for group in data["groups"]:
        folder=(ROOT/group["folder"]).resolve()
        if not folder.is_relative_to(root):
            raise RuntimeError("Invalid release integrity path")
        if group.get("optional") and not folder.exists():
            continue
        for file_info in group["files"]:
            path=(folder/file_info["name"]).resolve()
            if not path.is_relative_to(folder) or not path.is_file():
                raise RuntimeError("A required HALO model or asset is missing: "+file_info["name"])
            if path.stat().st_size!=file_info["size"]:
                raise RuntimeError("A HALO model or asset has changed: "+file_info["name"])
            with path.open("rb") as stream:
                if hashlib.file_digest(stream,"sha256").hexdigest()!=file_info["sha256"]:
                    raise RuntimeError("A HALO model or asset has changed: "+file_info["name"])
