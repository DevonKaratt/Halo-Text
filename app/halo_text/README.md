# halo_text

HALO's Python package. `app.py` owns the floating H, menus, background worker, caption scheduling, window-follow selection, audio controls, and speed check. `pipeline.py` joins OCR and translation; `core.py` holds shared text, boxes, and caches.

| Files | Purpose |
| --- | --- |
| `capture.py`, `windows.py` | Screen mapping/capture and Windows window tracking |
| `ocr.py`, `ocr_packs.py`, `source_language.py` | Built-in OCR, optional script readers, and input-language detection |
| `translation.py`, `online.py`, `indic_translation.py`, `pair_models.py` | Offline/online translation and downloadable pairs |
| `overlay.py`, `outline.py`, `floating.py`, `subtitles.py` | On-screen text, border, H icon, and audio subtitles |
| `audio.py`, `audio_core.py`, `voice.py`, `local_voice.py` | Speech capture/recognition, approximate voice labels, and output |
| `config.py`, `languages.py`, `paths.py`, `ipc.py` | Settings, catalog, project paths, and single-instance control |
| `*_setup.py`, `model_setup.py`, `model_manager.py` | Optional downloads and safe model removal |
| `demo.py`, `evaluation.py` | Generated fixtures and measurements |
| `fonts.py`, `release_integrity.py`, `__init__.py` | Font loading, packaged-asset verification, and version |

Normal screen text, audio, and translations stay in memory. Generated verification data goes to `../../reports/`.


Audio modules: audio.py captures/recognizes English; audio_core.py segments speech and estimates pitch; speech_setup.py installs the pinned recognition model; voice.py manages spoken output and bounded playback; local_voice.py synthesizes Hindi; voice_setup.py installs pinned stock Hindi voices. Spoken output defaults to 1.5×.

model_manager.py inventories and safely removes project-owned model folders, guarding active and shared language packs. app.py exposes this in the H controls.
