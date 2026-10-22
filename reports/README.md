# reports

Generated verification evidence and the presentation-ready `TEAM_SUMMARY.md`. JSON files hold measured timings and native-check results; PNG files are synthetic screen fixtures or previews. `evaluation/` groups OCR/layout cases, `language-check/` holds generated catalog checks, and `audio/` holds generated speech fixtures and measurements. These files are retained as evidence, not loaded by the application during normal use.

`caption_latency*.json`, `caption_polling_*.json`, and `caption_speed_comparison.json` describe older controlled caption experiments. `russian_caption_smoke.json` records generated Russian-to-English recognition and translation. Measurements from different models, hardware states, or test versions should not be treated as directly comparable. These checks do not establish accuracy for arbitrary movies or human translation quality. The automated suite passed 116 tests on 22 October 2026.
