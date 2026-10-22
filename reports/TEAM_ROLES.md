# HALO TEXT: four-member ownership plan

This plan assigns **primary ownership** of the current Windows application. Replace Member 1–4 with teammates' names. Ownership means the member implements changes, reviews related bugs, and keeps the listed files documented. Anyone may help test another area. Do not move files to match this plan; the current paths are part of the running app.

The `frontend/` folder, its downloadable ZIP, and website work are **out of scope for now** and are not assigned to any member.

## Member 1 — Screen Reading and Input Languages

**Result to own:** capture the selected area, find and read text quickly, identify its input language, and manage OCR language packs. Maintain reliable reading of changing captions.

**Application files:** `app/halo_text/capture.py`, `ocr.py`, `ocr_packs.py`, `source_language.py`, `pipeline.py`, `core.py`, `evaluation.py`, `demo.py`.

**Test files:** `tests/test_caption_ocr.py`, `test_core.py`, `test_freshness.py`, `test_multilingual.py`, `test_watch_languages.py`, `caption_latency.py`, `caption_benchmark.py`, `caption_benchmark_optimized.py`, `catalog_live_check.py`, `latin_smoke.py`, `multilingual_smoke.py`.

**Acceptance check:** English captions are recognized without an unnecessary online language check; installed non-English OCR readers work; an unknown script produces a clear pack prompt rather than silently stopping.

## Member 2 — Translation and Language Models

**Result to own:** choose online or offline translation, download and verify optional model packs, manage installed models, and keep language switching responsive.

**Application files:** `app/halo_text/languages.py`, `translation.py`, `online.py`, `indic_translation.py`, `indic_setup.py`, `model_setup.py`, `model_manager.py`, `pair_models.py`, `paths.py`.

**Folders and files:** `models/` including its README, provenance file, installed OCR/translation/speech/voice packs, and their upstream notices; `setup/` including dependency lists, installer, license, template, and README. Treat downloaded binaries as replaceable installed data, not hand-edited source. Member 2 maintains `.venv/` dependency setup; nobody edits package files inside it.

**Test files:** `tests/test_translation.py`, `test_model_manager.py`, `test_model_warmup.py`, `test_expansion.py`, `indic_live_check.py`.

**Acceptance check:** a requested available pack downloads or resumes, verifies, appears in Downloaded language models, translates, and can be removed safely. An unavailable offline pair gives a clear online option. Check Tamil, Telugu, and Malayalam with the shared Indian-language pack.

## Member 3 — Overlay, Controls, and Windows App

**Result to own:** show translated text in the selected region, keep the selection border visible, provide the floating H and controls, and keep the Windows app running in the background.

**Application files:** `Start Halo.pyw`, `app/launch.pyw`, `app/run.py`, `app/halo_text/__init__.py`, `app.py`, `config.py`, `floating.py`, `ipc.py`, `outline.py`, `overlay.py`, `fonts.py`, `font_setup.py`, `subtitles.py`, `windows.py`, `release_integrity.py`.

**Folders and files:** `assets/` including fonts, font licenses, and its READMEs; `settings/` including `config.json` and README; root `README.md`; `app/README.md`; `app/halo_text/README.md`. Keep the root launch path simple. `runtime/` is generated app state; Member 3 owns its layout, logging behavior, and README, while each member investigates logs from their area.

**Test files:** `tests/test_overlay.py`, `test_layout.py`, `test_floating.py`, `test_caption_stream.py`, `test_caption_timing.py`, `test_hardening.py`, `test_new_features.py`, `caption_layout_check.py`, `caption_movie_smoke.py`, `controller_smoke.py`, `floating_smoke.py`, `lifecycle_smoke.py`, `native_smoke.py`, `watch_smoke.py`, `window_follow_smoke.py`.

**Acceptance check:** dragging a box starts watching; the border remains; a translation that is longer than the original glyphs is visible within the selected region; pause, resume, clear, hotkeys, and right-click H work. Test on a generated moving caption window, not just through unit tests.

## Member 4 — Audio and End-to-End Quality

**Result to own:** capture system or microphone audio, recognize English speech, produce translated subtitles or speech, and run the final integrated checks before a demo.

**Application files:** `app/halo_text/audio.py`, `audio_core.py`, `local_voice.py`, `speech_setup.py`, `voice.py`, `voice_setup.py`.

**Folders and files:** `reports/` including test output, screenshots, `TEAM_SUMMARY.md`, this plan, and its README; `.pytest_cache/` is disposable test state. Member 4 maintains `tests/README.md` and `tests/conftest.py`, collects the four members' results, and signs off on integrated behavior. The test scripts themselves stay with their feature owners above.

**Test files:** `tests/test_audio_voice.py`, `audio_native_smoke.py`, `audio_pipeline_check.py`.

**Acceptance check:** both audio inputs can be selected; speech model availability and failures are shown clearly; subtitle-only, speech-only, and combined output work; output voice and speed controls behave as selected. Before the demo, run the automated suite and the native caption, model download, and audio checks with the other owners.

## Working agreement

1. Each member works primarily in their assigned files. For a change crossing areas, the owner of the affected file makes or reviews that edit.
2. Shared integration points are `pipeline.py` (Member 1), `app.py` (Member 3), and model selection (Member 2). Agree on the behavior at these boundaries before merging simultaneous changes.
3. Keep generated `runtime/`, `reports/`, `.pytest_cache/`, and installed `models/` data out of hand-written code reviews. Preserve upstream model and font license files.
4. Member 4 records a demo checklist and actual results. A passing unit suite alone does not establish that translated text is visible on screen.
