"""HALO TEXT entry point. Normal launch has no application window."""
import argparse
import json
import sys
sys.pycache_prefix = str(__import__("pathlib").Path(__file__).resolve().parents[1]/"runtime/bytecode")
from halo_text.paths import configure

def main():
    configure()
    parser = argparse.ArgumentParser(description="HALO TEXT: English-source translation overlay")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true", help="Check dependencies and run a local translation")
    modes.add_argument("--demo", action="store_true", help="Open a sample English document for testing")
    modes.add_argument("--benchmark", action="store_true", help="Run the pipeline on a generated sample, save timing/preview")
    modes.add_argument("--status", action="store_true", help="Read background application status")
    modes.add_argument("--stop", action="store_true", help="Gracefully stop the background application")
    modes.add_argument("--evaluate", action="store_true", help="Evaluate multiple generated screen layouts")
    from halo_text.languages import LANGUAGES
    modes.add_argument("--install-model", choices=LANGUAGES, metavar="LANG", help="Install a free local target model")
    modes.add_argument("--languages", action="store_true", help="List supported languages and installed models")
    modes.add_argument("--original", action="store_true", help="Toggle original text in the running app")
    modes.add_argument("--install-indic",action="store_true",help="Install the offline Bodo/Kashmiri Indian language pack")
    modes.add_argument("--install-voices",action="store_true",help="Install local Hindi speech output voices")
    modes.add_argument("--install-audio",action="store_true",help="Download the optional CPU speech model")
    from halo_text.ocr_packs import PACKS
    modes.add_argument("--install-ocr", choices=PACKS, metavar="PACK", help="Download an optional source OCR pack")
    modes.add_argument("--install-pair", nargs=2, metavar=("SOURCE", "TARGET"), help="Download a direct offline translation pair")
    modes.add_argument("--audio-devices",action="store_true",help="List default audio inputs without recording")
    modes.add_argument("--audio-stop",action="store_true",help="Stop live audio subtitles")
    modes.add_argument("--audio-file",metavar="PATH",help="Transcribe and translate an audio file locally")
    parser.add_argument("--target", choices=LANGUAGES, help="Override the starting target for this run")
    args = parser.parse_args()
    if args.target and any((args.status,args.stop,args.install_model,args.install_indic,args.languages,args.original,args.install_audio,args.install_voices,args.audio_devices,args.audio_stop)):
        parser.error("--target applies to launching, --check, --demo, --benchmark or --evaluate")
    if args.install_indic:
        from halo_text.indic_setup import install
        install()
        return 0
    if args.install_voices:
        from halo_text.voice_setup import install
        install()
        return 0
    if args.install_audio:
        from halo_text.speech_setup import install
        install()
        return 0
    if args.install_ocr:
        from halo_text.ocr_packs import install
        print(f"Installed OCR pack: {install(args.install_ocr)}", flush=True)
        return 0
    if args.install_pair:
        from halo_text.pair_models import install
        print(f"Installed offline pair: {install(*args.install_pair)}", flush=True)
        return 0
    if args.audio_devices:
        from halo_text.audio import device_summary
        print(json.dumps(device_summary(),indent=2))
        return 0
    if args.audio_stop:
        from halo_text.ipc import request
        print(json.dumps(request("audio-stop"),indent=2))
        return 0
    if args.install_model:
        from halo_text.model_setup import install
        install(args.install_model)
        return 0
    if args.languages:
        from halo_text.model_setup import installed_languages
        print(json.dumps(installed_languages(),indent=2))
        return 0
    if args.original:
        from halo_text.ipc import request
        print(json.dumps(request("original"),indent=2))
        return 0
    if args.status or args.stop:
        from halo_text.ipc import request
        print(json.dumps(request("stop" if args.stop else "status"),indent=2))
        return 0
    from halo_text.windows import enable_dpi_awareness, require_windows
    require_windows()
    enable_dpi_awareness()
    from halo_text.pipeline import preload_runtime
    preload_runtime()
    from dataclasses import replace
    from halo_text.config import load_config
    config=load_config()
    if args.target:
        config=replace(config,target=args.target)
    if args.audio_file:
        from halo_text.audio import decode_audio_file as decode_audio
        from halo_text.audio import SpeechEngine
        engine=SpeechEngine(config)
        samples=decode_audio(args.audio_file,sampling_rate=16000)
        result=engine.process(samples)
        print(json.dumps({"source":"en","target":config.target,"english":result[0] if result else "",
                          "translated":result[1] if result else ""},ensure_ascii=True,indent=2))
        return 0
    if args.check:
        from importlib.metadata import version
        from halo_text.config import load_config
        from halo_text.model_setup import find_model
        from halo_text.online import route
        from halo_text.indic_setup import DIRECTORY as indic_directory
        from halo_text.pipeline import Pipeline
        pipeline = Pipeline(config)
        recognized = pipeline.warmup()
        translation = pipeline.translator.translate_many(["Welcome to our project."])[0]
        if config.target == "hi" and not any("\u0900" <= ch <= "\u097f" for ch in translation):
            raise RuntimeError("Hindi translation check did not produce Devanagari text.")
        selected=route(config)
        model=indic_directory if selected=="indic" else find_model(config.target)
        print(json.dumps({"status":"ok","backend":config.backend,"provider":selected,"target":config.target,"model":str(model) if model else None,
                          "translation":translation,"recognized":recognized,
                          "versions":{p:version(p) for p in
                                      ("rapidocr","onnxruntime","ctranslate2","PySide6-Essentials")}},
                         ensure_ascii=True,indent=2))
        return 0
    if args.evaluate:
        from halo_text.evaluation import main as evaluate_main
        return evaluate_main(config=config)
    if args.demo or args.benchmark:
        from halo_text.demo import main as demo_main
        return demo_main(benchmark=args.benchmark,config=config)
    from halo_text.app import run
    return run(config=config)

if __name__ == "__main__":
    raise SystemExit(main())
