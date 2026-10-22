# tests

`test_*.py` is the automated suite; `conftest.py` keeps temporary files under `../runtime/`. From the top folder run `.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider`. The last full run passed 107 tests on 20 October 2026. Tests use generated samples, not user screen content.

The suite checks screen/caption scheduling, translation caching and multilingual routing, persistent overlays, model deletion safeguards, audio segmentation/output controls, window-follow geometry, configuration, packaging, and startup behavior. `test_new_features.py` covers changed-sentence reuse, approximate voice labels, and window-follow movement.

Scripts ending in `_smoke.py` run generated native-window checks; close HALO first. `lifecycle_smoke.py` starts and stops the app, and `window_follow_smoke.py` verifies binding to a sample window in another process. Older `controller_smoke.py` assumes a local Hindi model and needs that pack installed. Caption benchmark scripts and `evaluation.py` write synthetic measurements under `../reports/`. `catalog_live_check.py` and `audio_pipeline_check.py` contact the approved online services using generated text; run them only when an online check is intended.
