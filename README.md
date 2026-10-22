# HALO TEXT

HALO is a Python Windows background app that reads visible text in a selected screen area, translates it, and draws the result over the original position. Double-click **Start Halo.pyw** to launch it. Right-click the floating blue **H** or tray icon for all controls. The app has no login.

## First use

1. If the project environment is not installed, run `python setup/setup_halo.py` from this folder. Setup creates `.venv`, installs the pinned Python dependencies, and prepares the saved output language. Internet access is needed for downloads.
2. Double-click **Start Halo.pyw** and wait for the ready notification.
3. Right-click **H → Translation language** to choose the output. English screen OCR is built in. For another input script, open **Input OCR language packs** and download its reader. HALO can prompt for a reader when it recognizes another language but the pack is missing.
4. Press **Ctrl+Alt+R**, drag around the text, and release. The border stays visible. Green means watching; amber means paused.
5. For video, select only the subtitle strip and enable **Faster captions**. **Keep last caption until replacement** holds the previous translation while HALO works on the next one. Complete unchanged sentences reuse cached translations; changed text is translated again.

The selected box follows its underlying application window when that window moves or resizes on the same display. Turn **Follow selected window when it moves or resizes** off in H controls if you want a fixed screen region. Select a new area if the window crosses displays.

| Shortcut | Action |
| --- | --- |
| Ctrl+Alt+R | Select a screen area |
| Ctrl+Alt+T | Translate the current area |
| Ctrl+Alt+A | Pause or resume watching |
| Ctrl+Alt+O | Show original or translated text |
| Ctrl+Alt+C | Clear translation and selection |
| Ctrl+Alt+F | Translate the display under the pointer |
| Ctrl+Alt+S | Start or stop audio translation |
| Ctrl+Alt+Q | Exit |

## Languages and models

The output menu lists English, 22 scheduled Indian languages, and 30 other global languages. Input recognition depends on the writing-system OCR pack. Short captions and languages sharing a script may be misidentified; **H → Input language** provides a manual choice when its OCR pack is installed. HALO asks Google's keyless text endpoint to identify ambiguous *recognized text*. It does not send screenshots. If OCR reads no characters, choose a likely script under **Input OCR language packs**.

For a non-English source, HALO offers online translation or an available direct offline source-to-target pack. Online translation sends recognized text to Google's unofficial public endpoint; availability and speed can vary. If that service rate-limits a watched area, HALO keeps watching and retries after a short delay. Local models run on the CPU. **H → Downloaded language models** shows installed OCR, translation, and audio packs and lets you remove packs you no longer use. Removing an unused pack frees storage; it does not by itself speed up the active translation. A removed pack can be downloaded again. All 22 Indian output languages share a large optional pack of about 850 MB; interrupted downloads resume from saved chunks.

## Live audio

Open **H → Audio translation and voice** and choose System audio or Microphone. English speech recognition needs its optional downloaded speech model. Select **Subtitles and speech**, **Subtitles only**, or **Speech only**. Translated speech uses an available local or online voice; online voices send translated text to Microsoft's speech service. Speaking speed, voice, output device, feedback prevention, and subtitle display delay (0–3 seconds) are in the same menu. Optional voice labels group broad pitch ranges; they are approximate and do not identify speakers. The app does not reproduce a person's voice identity.

## Speed check and limits

**H → Check speed on this computer** measures OCR on the selected area and, when an offline output model is installed, local translation on sample text. It reports whether DirectML is present, but HALO currently uses CPU OCR and does not automatically enable GPU acceleration. The check excludes capture, online latency, and display time. A narrow selection and an installed offline model usually avoid unnecessary work, but no fixed sub-second latency is guaranteed. Audio recognition and spoken output can lag rapid dialogue.

## Files and development

| Folder | Purpose |
| --- | --- |
| `app/` | Python application, internal launcher, OCR, translation, overlay, audio, and Windows integration |
| `assets/` | Bundled fonts and license notices |
| `frontend/` | Informational page, manual, and portable Windows release builder |
| `models/` | User-downloaded optional OCR, translation, and speech packs with provenance |
| `reports/` | Generated verification evidence and [team summary](reports/TEAM_SUMMARY.md) |
| `runtime/` | Changing logs, position, caches, temporary files, and Python bytecode |
| `settings/` | Startup defaults and optional local override |
| `setup/` | Setup script, pinned dependencies, and MIT license |
| `tests/` | Automated and generated-window checks |
| `.venv/` | Managed third-party Python environment; leave its internals intact |

Each project-owned folder has one README describing its contents. Generated model folders keep their upstream licenses and model cards. To change startup defaults, edit `settings/config.json` or create `settings/config.local.json`, then restart. Menu changes are session-only.

For the four-member development split and exact file ownership, see [TEAM_ROLES.md](reports/TEAM_ROLES.md). Frontend work is currently excluded from that split.

The automated suite passed **116 tests** on 22 October 2026. Native startup and a sample-window movement check also passed. Use `.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider` for automated checks; native smoke scripts are described in `tests/README.md`. Tests and reports use generated samples, not a representative real-world accuracy study.

Open `frontend/index.html` locally for the information page and `frontend/manual.html` for user instructions. The page links to the portable Windows ZIP in `frontend/downloads/`. The ZIP is a generated release artifact and is not stored in Git; build it locally or attach it to a GitHub Release before publishing the site. Extract the entire ZIP to a writable folder and run `HaloText.exe`; the floating H opens its controls. The ZIP starts without optional language or speech packs, which users can download from the controls. To offer the download on a public website, host the complete `frontend/` folder with the built ZIP so the relative link stays valid. HALO's own source is [MIT licensed](LICENSE); bundled models, fonts, and libraries retain their separate terms.

Normal screen and audio content stays in memory. Online translation sends recognized text, and online voice service sends translated text. Generated test artifacts are stored in `reports/`; startup and model-download errors are logged in `runtime/state/`.
