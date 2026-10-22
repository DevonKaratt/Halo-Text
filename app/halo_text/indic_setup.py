"""Install the reviewed, public IndicTrans2 CPU pack with verified resumable downloads."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import time
import requests
from .paths import ROOT,MODELS,configure

REPO="adalat-ai/ct2-rotary-indictrans2-en-indic-dist-200M"
REVISION="ee04de9a86e42920ac310a0fe5a1505c85671b68"
PREFIX="en-indic-200m-ct2/ctranslate2_model/"
DIRECTORY=MODELS/"indictrans2"
TARGET_TAGS={
 "as":"asm_Beng", "bn":"ben_Beng", "brx":"brx_Deva", "doi":"doi_Deva",
 "gu":"guj_Gujr", "hi":"hin_Deva", "kn":"kan_Knda", "ks":"kas_Arab",
 "gom":"gom_Deva", "mai":"mai_Deva", "ml":"mal_Mlym", "mni-Mtei":"mni_Mtei",
 "mr":"mar_Deva", "ne":"npi_Deva", "or":"ory_Orya", "pa":"pan_Guru",
 "sa":"san_Deva", "sat":"sat_Olck", "sd":"snd_Arab", "ta":"tam_Taml",
 "te":"tel_Telu", "ur":"urd_Arab",
}
FILES={
 "config.json":(197,"10874b31f398169314575b99a04560b6d8944fba1c7a0d96eb89f7676bf08979"),
 "model.bin":(847151318,"2b4b4c195008f27e97f39be503f470b583c22fd670e67a9a886431df61348eba"),
 "source_vocabulary.json":(543560,"66919522447d51be41250cc780c656e2ef495c403f96a7e4294dc36472524b8d"),
 "target_vocabulary.json":(4531604,"7f28e3f24fcd0a203eb307e8c56ac0b99350a6a1562c25b6e8ffd97d6016878c"),
 "vocab/model.SRC":(759425,"3cedc5cbcc740369b76201942a0f096fec7287fee039b55bdb956f301235b914"),
 "vocab/model.TGT":(3256903,"ac9257c8e76b8b607705b959cc3d075656ea33032f7a974e467b8941df6e98d4"),
}

def installed():
    return (DIRECTORY/"source.json").is_file() and all((DIRECTORY/name).is_file() for name in FILES)

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def download_file(name,size,sha):
    target=DIRECTORY/name
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.is_file() and target.stat().st_size==size and digest(target)==sha:
        return
    url=f"https://huggingface.co/{REPO}/resolve/{REVISION}/{PREFIX}{name}"
    parts=ROOT/"runtime/cache"/"indic-parts"/name.replace("/","_")
    parts.mkdir(parents=True,exist_ok=True)
    step=4*1024*1024
    count=(size+step-1)//step
    def fetch(index):
        start=index*step
        end=min(size,start+step)-1
        part=parts/str(index)
        if part.is_file() and part.stat().st_size==end-start+1:
            return
        for attempt in range(5):
            try:
                with requests.get(url,params={"download":"true","halo_part":str(index)},
                                  headers={"Range":f"bytes={start}-{end}"},
                                  timeout=(15,35),stream=True) as response:
                    response.raise_for_status()
                    if size>step and (response.status_code!=206 or
                            not response.headers.get("Content-Range","").startswith(f"bytes {start}-{end}/")):
                        raise RuntimeError("Model server did not honor the requested range.")
                    data=b"".join(response.iter_content(256*1024))
                if len(data)!=end-start+1:
                    raise RuntimeError("Incomplete model range")
                part.write_bytes(data)
                return
            except Exception:
                if attempt==4:
                    raise
                time.sleep(min(2+attempt,5))
    print("Downloading "+name,flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for done,_ in enumerate(pool.map(fetch,range(count)),1):
            if done%10==0 or done==count:
                print(f"{name}: {done}/{count} ranges",flush=True)
    temporary=target.with_suffix(target.suffix+".part")
    with temporary.open("wb") as output:
        for index in range(count):
            output.write((parts/str(index)).read_bytes())
    if digest(temporary)!=sha:
        temporary.unlink()
        raise RuntimeError("Downloaded model hash mismatch.")
    temporary.replace(target)
    for index in range(count):
        (parts/str(index)).unlink()

def install():
    configure()
    DIRECTORY.mkdir(exist_ok=True)
    for name,(size,sha) in FILES.items():
        download_file(name,size,sha)
    (DIRECTORY/"source.json").write_text(json.dumps({
        "repository":REPO,"revision":REVISION,"upstream":"AI4Bharat/IndicTrans2",
        "license":"MIT","files":FILES},indent=2),encoding="utf-8")
    print("Verified local Indian-language pack installed.",flush=True)
    return DIRECTORY

if __name__=="__main__":
    install()
