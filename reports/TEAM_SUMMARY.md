# HALO TEXT — project summary (20 October 2026)

HALO TEXT is a Python-based Windows application that translates visible screen text in its original position. English OCR is built in, and optional OCR packs can read supported additional writing systems. The user selects an area, HALO recognizes the text, identifies its likely source language, translates it into a chosen output language, and places the result over the source. It works as a background application controlled through a small movable blue **H** icon, the system tray, and keyboard shortcuts.

## Project idea and workflow

1. The user starts HALO and chooses an output language from the H menu.
2. The user drags a rectangle around the text or video subtitle strip. A visible border marks the selected area.
3. HALO captures that rectangle, finds text with OCR, identifies the likely source language, sends recognized text to the selected translation route, and paints the translated result in the same screen region. A non-English source needs a suitable OCR writing-system pack first; HALO then offers online translation or an available direct offline pair.
4. With automatic watching enabled, HALO checks the same rectangle when its content changes. Scrolling a page or displaying the next caption can trigger another translation without redrawing the box.
5. The user can pause watching, view the original, request another translation, change languages, or clear the selection from the floating H or a shortcut.

The screen pipeline has separate capture, OCR, translation, and overlay stages. HALO processes OCR and translation in a background worker so the controls remain responsive. It rejects results from older selections, caches repeated translations, and skips an identical captured caption strip. The overlay and border are excluded from screen captures to prevent HALO from reading its own output.

## Implemented features

| Feature | Behavior available in the application |
| --- | --- |
| Floating control | A draggable blue circular H can be placed around the screen. Right-clicking opens the controls; double-clicking begins area selection. Its position is remembered. A system-tray menu offers the same core controls. |
| Screen selection | The user drags a box over text. The outline remains visible after translation: green while watching and amber while paused. The area can be reselected or cleared. |
| Text overlay | Recognized text is translated and drawn near its original position. The user can toggle the original text for comparison. Overlay windows allow normal interaction with the application beneath them. |
| Automatic updates | HALO watches the chosen rectangle for changed screen content. For documents it clears outdated text, waits briefly for content to settle, and translates new text. In Faster captions it can hold the previous translation until a replacement is ready. This supports scrolling pages and changing captions. |
| Faster captions | A mode optimized for a narrow subtitle strip uses quicker checking and caption-specific OCR processing. Selecting only the subtitle area reduces the image HALO must read. Identical captured strips are skipped. |
| Input OCR packs | English OCR is built in. The H menu can download and remove optional script packs such as Cyrillic, Latin, Arabic, Devanagari, Tamil, Telugu, Chinese, Japanese, Korean, and Thai. A browse-by-language list shows pack availability; the **Input language** menu offers automatic detection or a manual override when short captions are ambiguous. |
| Output languages | The controls group 22 Indian-language entries, 30 other global-language entries, and English. One output language is selected at a time. |
| Translation routes | Available offline packs run locally on the CPU. For detected non-English input, HALO asks whether to use the approved keyless Google Translate public endpoint or download a direct Argos offline pair if available. Online translation sends recognized text rather than screenshots. Russian-to-English was verified through both routes. |
| Model management | The user can download an available offline pack for the selected language. **Downloaded language models** lists installed translation and audio packs with approximate sizes, offers removal with confirmation, and protects a pack currently in use. All 22 Indian outputs share one optional English-source translation pack. |
| Audio translation | HALO can take English speech from the microphone or Windows system audio, recognize it with an optional local speech model, translate the recognized text, and speak the result when a suitable voice is available. Voice controls include output voice, device, pitch, and speaking speed; 1.5× is offered. |
| Status and recovery | The H controls show current mode and provide shortcut help. HALO supports starting, querying status, stopping, and preventing duplicate background launches. Configuration, logs, and saved icon position stay in project folders. |
| Information page and manual | A simple static project page and a user manual explain setup, controls, model choices, and download steps. Its download button links to a verified portable Windows ZIP that launches from a fresh extraction. HALO's own source is MIT licensed. |

## How to demonstrate it

1. Double-click `Start Halo.pyw` in the HALO TEXT folder. The blue H should appear; right-click it to show the menu and keyboard shortcuts.
2. Open **Translation language** and select an output. For non-English input, open **Input OCR language packs** and download its writing-system pack; Russian captions need **Cyrillic**. An optional direct offline translation pair can be downloaded when prompted.
3. Open an English page or video. Press **Ctrl+Alt+R**, then drag a rectangle around the text. For video, enable **Faster captions** and select only the subtitle strip.
4. Observe the translated text over the selected area and the persistent border. Scroll the page or wait for the next caption to show automatic updating. Use **Ctrl+Alt+O** to compare with the original.
5. Open **Downloaded language models** to show installed packs and their sizes. To demonstrate removal, select a pack marked **remove** and confirm. Switch to a different output first if a translation pack is marked **in use**; stop audio before removing an audio pack.
6. For an audio demonstration, install **English speech recognition** from the model menu. Open **Audio translation and voice**, choose **System audio** or **Microphone**, then enable spoken output and select a voice when available.

| Shortcut | Action |
| --- | --- |
| **Ctrl+Alt+R** | Select a screen area |
| **Ctrl+Alt+A** | Pause or resume automatic watching |
| **Ctrl+Alt+T** | Translate the selected area again |
| **Ctrl+Alt+O** | Show or hide the original text |
| **Ctrl+Alt+C** | Clear the translation and selection border |
| **Ctrl+Alt+S** | Stop audio listening and speech |
| **Ctrl+Alt+Q** | Exit HALO |

Removing downloaded packs frees storage space. It does not directly make the active translation faster because HALO loads only the selected translation model. Downloaded packs can be installed again from the H menu. The Windows ZIP contains no preinstalled optional OCR, translation, or speech packs, so each user can choose only those they need; English OCR remains built in.

## Additional live-use features

Fast captions retain the previous translation until a replacement is ready. Complete unchanged sentences reuse cached translations, while changed text is translated again. A selected box can follow its underlying application window when it moves or resizes on the same display. Audio output offers subtitles and speech, subtitles only, or speech only, with adjustable subtitle delay and approximate pitch-based voice labels. The labels are not reliable speaker identification. The H menu measures OCR on the selected area and local translation when installed, and reports whether DirectML is available; GPU acceleration is not automatically enabled.

## Implementation and verification evidence

HALO is implemented in Python. The Windows interface uses PySide6; screen capture, OCR, translation, and optional speech are connected through the application pipeline. Offline translation uses pretrained CPU model packs; online translation and voices are optional routes approved for this project. HALO integrates these components rather than claiming to have trained a new OCR, translation, or speech model.

The Python regression suite passed **107 tests on 20 October 2026**. A generated Russian caption was recognized in Cyrillic and translated to “Welcome to our project” in English through both online and downloaded offline routes. A generated Spanish caption was also detected and translated to English online after a temporary Latin OCR pack was installed; that test pack was removed afterward. Generated checks also cover caption reading, language routing, model-removal safeguards, automatic watching, audio behavior, and interface logic. Earlier native Windows checks exercised selecting an area, persistent borders, floating controls, click-through overlays, hotkeys, and background lifecycle. A synthetic Tamil caption run measured roughly **0.77–0.82 seconds** for four uncached narrow-caption examples after warm-up; a warmed second Russian caption took about **0.17 seconds** for OCR and offline translation. These measurements exclude screen-change detection, capture, and painting and are not fixed live-video latency or general translation-accuracy scores. The current OCR pack catalogue covers selected scripts rather than every language or writing system. Detailed evidence and historical measurements are in this `reports` folder.
