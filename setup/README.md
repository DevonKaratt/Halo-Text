# setup

`setup_halo.py` creates/repairs the project-local `.venv` and prepares the selected output model. From the top folder run `python setup/setup_halo.py`; add `--with-audio` for English speech recognition and, when Hindi is selected, local Hindi voices. `--target CODE` overrides the saved output language.

`requirements.txt` lists runtime packages, `requirements.lock.txt` pins them, `requirements-dev.txt` adds test tools, and `requirements-build.txt` adds release-building tools. The root `LICENSE` covers HALO's own source; third-party packages and models keep their separate licenses. The root `.gitignore` controls which local files enter Git.

Setup follows the saved output language unless `--target` is supplied, so removed optional models are not all reinstalled. It attempts an offline model for that target and can fail when no direct pack exists; online-only languages can instead be selected in HALO with automatic online routing.
