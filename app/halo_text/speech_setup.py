"""Pinned, verified small English CPU speech model; downloads are explicit."""
import concurrent.futures,hashlib,json,time
from pathlib import Path
import requests
from .paths import ROOT,MODELS,configure
REPOSITORY="Systran/faster-whisper-tiny.en"
REVISION="0d3d19a32d3338f10357c0889762bd8d64bbdeba"
SPEECH_MODEL=MODELS/"speech-tiny.en"
REQUIRED=("config.json","model.bin","tokenizer.json","vocabulary.txt")
def installed():
    return (SPEECH_MODEL/"source.json").is_file() and all((SPEECH_MODEL/n).is_file() for n in REQUIRED)
def install():
    configure()
    if installed():
        print("English speech model already installed.",flush=True);return SPEECH_MODEL
    meta=requests.get(f"https://huggingface.co/api/models/{REPOSITORY}/revision/{REVISION}",params={"blobs":"true"},timeout=40)
    meta.raise_for_status();files={x["rfilename"]:x for x in meta.json()["siblings"]}
    SPEECH_MODEL.mkdir(parents=True,exist_ok=True);hashes={}
    for name in REQUIRED:
        info=files[name];size=info["size"];parts=ROOT/"runtime/cache/speech-parts"/name
        parts.mkdir(parents=True,exist_ok=True);step=4*1024*1024;count=(size+step-1)//step
        def fetch(i):
            start=i*step;end=min(size,start+step)-1;part=parts/str(i)
            if part.exists() and part.stat().st_size==end-start+1:return
            for attempt in range(4):
                try:
                    with requests.get(f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}",params={"download":"true","halo_part":i},headers={"Range":f"bytes={start}-{end}"},timeout=(15,40),stream=True) as r:
                        r.raise_for_status()
                        if size>step and (r.status_code!=206 or not r.headers.get("Content-Range","").startswith(f"bytes {start}-{end}/")):raise RuntimeError("Speech server did not honor range")
                        data=b"".join(r.iter_content(262144))
                    if len(data)!=end-start+1:raise RuntimeError("Incomplete speech range")
                    part.write_bytes(data);return
                except Exception:
                    if attempt==3:raise
                    time.sleep(1+attempt)
        print("Downloading "+name,flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(fetch,range(count)))
        target=SPEECH_MODEL/name;temp=target.with_suffix(target.suffix+".part")
        with temp.open("wb") as out:
            for i in range(count):out.write((parts/str(i)).read_bytes())
        data=temp.read_bytes();sha=hashlib.sha256(data).hexdigest()
        valid=sha==info["lfs"]["sha256"] if info.get("lfs") else hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()==info["blobId"]
        if not valid:temp.unlink();raise RuntimeError("Speech model integrity check failed")
        temp.replace(target);hashes[name]=sha
        for i in range(count):(parts/str(i)).unlink()
    (SPEECH_MODEL/"source.json").write_text(json.dumps({"repository":REPOSITORY,"revision":REVISION,"sha256":hashes},indent=2),encoding="utf-8")
    (SPEECH_MODEL/"README.md").write_text("# English speech recognition\n\nPinned Systran conversion of Whisper tiny.en, CPU int8. model.bin contains weights; tokenizer/vocabulary/config are required. source.json records revision and verified hashes. MIT upstream model license. English only; short chunks can lose context.\n",encoding="utf-8")
    print("English speech model ready.",flush=True);return SPEECH_MODEL
if __name__=="__main__":install()
