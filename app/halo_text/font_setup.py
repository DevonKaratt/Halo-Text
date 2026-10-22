"""Project-local fonts for scripts not reliably supplied by Windows."""
import base64
import hashlib
import json
import requests
from .paths import ROOT,configure

FONTS=ROOT/"assets"/"fonts"
PACKAGES={
 "notosanssc":"NotoSansSC[wght].ttf",
 "notosansolchiki":"NotoSansOlChiki[wght].ttf",
 "notosansmeeteimayek":"NotoSansMeeteiMayek[wght].ttf",
}
def install():
    configure()
    FONTS.mkdir(parents=True,exist_ok=True)
    session=requests.Session()
    manifest=[]
    for directory,filename in PACKAGES.items():
        for name in (filename,"OFL.txt"):
            local=FONTS/(directory+"-"+name)
            if local.is_file():
                data=local.read_bytes()
                git_hash=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
                manifest.append({"file":local.name,"source":f"https://github.com/google/fonts/blob/main/ofl/{directory}/{name}","git_sha":git_hash})
                continue
            url=f"https://api.github.com/repos/google/fonts/contents/ofl/{directory}/{name}"
            r=session.get(url,timeout=(10,30))
            r.raise_for_status()
            metadata=r.json()
            expected_sha=metadata["sha"]
            source_url=metadata["html_url"]
            if metadata.get("encoding")!="base64":
                blob=session.get(metadata["git_url"],timeout=(10,90))
                blob.raise_for_status()
                metadata=blob.json()
            if metadata.get("encoding")!="base64":
                raise RuntimeError("Font API did not provide file contents.")
            data=base64.b64decode(metadata["content"])
            git_hash=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
            if git_hash!=expected_sha:
                raise RuntimeError("Font blob checksum mismatch.")
            local.write_bytes(data)
            manifest.append({"file":local.name,"source":source_url,"git_sha":git_hash})
            print("Installed "+local.name,flush=True)
    if manifest:
        (FONTS/"source.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return FONTS
if __name__=="__main__":
    install()
