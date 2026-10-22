"""Explicit installation of pinned local Hindi voices; no runtime downloads."""
import concurrent.futures,hashlib,json,time
from pathlib import Path
import requests
from .paths import ROOT,MODELS,configure
REPO="rhasspy/piper-voices"
REVISION="c10ece1aade47bb51c153c893d14e5bf8e5b7117"
DIRECTORY=MODELS/"voices-hi"
NAMES={"Male":"pratham","Female":"priyamvada"}
def model_path(gender):
    name=NAMES.get(gender,"priyamvada")
    return DIRECTORY/name/f"hi_IN-{name}-medium.onnx"
def installed():
    return (DIRECTORY/"source.json").is_file() and all(model_path(g).is_file() and Path(str(model_path(g))+".json").is_file() for g in NAMES)
def install():
    configure();DIRECTORY.mkdir(parents=True,exist_ok=True);manifest={}
    for name in NAMES.values():
        sub=f"hi/hi_IN/{name}/medium"
        response=requests.get(f"https://huggingface.co/api/models/{REPO}/tree/{REVISION}/{sub}",timeout=40);response.raise_for_status()
        for info in response.json():
            if info["type"]!="file":continue
            remote=info["path"];target=DIRECTORY/name/Path(remote).name;target.parent.mkdir(parents=True,exist_ok=True)
            size=info["size"]
            def verified(path):
                if not path.exists() or path.stat().st_size!=size:return False
                data=path.read_bytes()
                return hashlib.sha256(data).hexdigest()==info["lfs"]["oid"] if info.get("lfs") else hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()==info["oid"]
            if not verified(target):
                parts=ROOT/"runtime/cache/voice-parts"/name/target.name;parts.mkdir(parents=True,exist_ok=True)
                step=4*1024*1024;count=(size+step-1)//step
                def fetch(i):
                    start=i*step;end=min(size,start+step)-1;p=parts/str(i)
                    if p.exists() and p.stat().st_size==end-start+1:return
                    for attempt in range(4):
                        try:
                            with requests.get(f"https://huggingface.co/{REPO}/resolve/{REVISION}/{remote}",params={"download":"true","halo_part":i},headers={"Range":f"bytes={start}-{end}"},timeout=(15,40),stream=True) as r:
                                r.raise_for_status()
                                if size>step and (r.status_code!=206 or not r.headers.get("Content-Range","").startswith(f"bytes {start}-{end}/")):raise RuntimeError("Voice range unsupported")
                                data=b"".join(r.iter_content(262144))
                            if len(data)!=end-start+1:raise RuntimeError("Incomplete voice range")
                            p.write_bytes(data);return
                        except Exception:
                            if attempt==3:raise
                            time.sleep(1+attempt)
                print("Downloading local voice: "+target.name,flush=True)
                with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(fetch,range(count)))
                temp=target.with_suffix(target.suffix+".part")
                with temp.open("wb") as f:
                    for i in range(count):f.write((parts/str(i)).read_bytes())
                if not verified(temp):temp.unlink();raise RuntimeError("Voice integrity check failed")
                temp.replace(target)
                for i in range(count):(parts/str(i)).unlink()
            manifest[str(target.relative_to(DIRECTORY))]=hashlib.sha256(target.read_bytes()).hexdigest()
        (DIRECTORY/name/"README.md").write_text("# Local Hindi voice\n\nONNX weights, JSON phoneme/config data and upstream MODEL_CARD license/source notes. Required for offline synthesis; preserve the model card.\n",encoding="utf-8")
    (DIRECTORY/"source.json").write_text(json.dumps({"repository":REPO,"revision":REVISION,"sha256":manifest},indent=2),encoding="utf-8")
    (DIRECTORY/"README.md").write_text("# Local Hindi voices\n\nMale pratham and female priyamvada Piper voices. source.json records pinned files and hashes. Each subfolder retains its MODEL_CARD and license details. These are stock voices, not original-speaker clones.\n",encoding="utf-8")
    print("Local Hindi voices ready.",flush=True)
if __name__=="__main__":install()
