from pathlib import Path
from halo_text.paths import ROOT,MODELS,STATE
from halo_text.config import load_config

def test_project_paths_and_configuration_match_layout():
 assert ROOT.name=='Halo-Text'
 assert MODELS==ROOT/'models'
 assert STATE==ROOT/'runtime/state'
 from halo_text.languages import LANGUAGES
 assert load_config().target in LANGUAGES
 assert (ROOT/'app/run.py').is_file()
 assert (ROOT/'setup/requirements.lock.txt').is_file()

def test_root_has_launcher_readme_and_git_metadata():
 assert {p.name for p in ROOT.iterdir() if p.is_file()}=={'Start Halo.pyw','README.md','.gitignore','.gitattributes','LICENSE'}

def test_project_owned_folders_have_guides():
 for name in ['app','app/halo_text','settings','setup','assets','assets/fonts','models','tests','reports','runtime','runtime/state','runtime/temp','runtime/cache','runtime/bytecode','.venv']:
  assert (ROOT/name/'README.md').is_file(),name
