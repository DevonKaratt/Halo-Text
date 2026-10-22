# models

Optional downloaded language components live here. HALO's H menu lists complete installed packs and provides confirmed removal and re-download controls. Packs are not part of the intended public download.

- `ocr-<script>/` contains an optional RapidOCR detection and recognition model for source text in that writing system, plus `halo-ocr.json` identifying the pack. One OCR pack can serve several source languages using the same script.
- `translate-<source>_<target>/` contains a direct Argos offline translation pair. For example, `translate-ru_en` is Russian to English. The `metadata.json` and `source.json` files identify the language pair and origin.
- `indictrans2/`, when installed, provides the shared English-to-22-Indian-languages translation pack.
- `speech-tiny.en/` contains optional English audio recognition.
- `voices-hi/` contains optional local Hindi speaking voices.

English screen OCR is part of the core application. Other OCR writing-system packs are downloaded only when requested. Models have separate upstream licenses and provenance. Removing an OCR or translation pack disables its offline route until it is downloaded again; removing an unused pack frees disk space rather than directly speeding the active model.
