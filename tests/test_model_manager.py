from pathlib import Path
import pytest
from halo_text import model_manager


def test_model_catalogue_uses_direct_public_index_without_api_quota(monkeypatch):
    from halo_text import model_setup
    calls=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,*args):return b'[{"from_code":"en","to_code":"hi"}]'
    def open_index(request,timeout):
        calls.append(request.full_url)
        return Response()
    monkeypatch.setattr(model_setup.urllib.request,"urlopen",open_index)
    assert model_setup.read_index()==[{"from_code":"en","to_code":"hi"}]
    assert calls==[model_setup.INDEX]


def test_removal_protects_active_and_shared_language_pack(tmp_path,monkeypatch):
    root=tmp_path/'models';root.mkdir()
    folder=root/'indictrans2';folder.mkdir();(folder/'model.bin').write_bytes(b'model')
    entry=model_manager.ModelEntry('indic','Tamil, Telugu, Bodo, Kashmiri',folder,'translation',('ta','te','brx','ks'),5)
    monkeypatch.setattr(model_manager,'MODELS',root)
    monkeypatch.setattr(model_manager,'installed_models',lambda:[entry])
    with pytest.raises(RuntimeError,match='selected output language'):
        model_manager.remove_model('indic','ta')
    assert folder.is_dir()
    with pytest.raises(RuntimeError,match='selected output language'):
        model_manager.remove_model('indic','te')
    assert folder.is_dir()


def test_removal_is_limited_to_project_model_root(tmp_path,monkeypatch):
    root=tmp_path/'models';root.mkdir()
    other=tmp_path/'outside';other.mkdir();(other/'keep').write_text('keep')
    entry=model_manager.ModelEntry('translation:hi','Hindi',other,'translation',('hi',),4)
    monkeypatch.setattr(model_manager,'MODELS',root)
    monkeypatch.setattr(model_manager,'installed_models',lambda:[entry])
    with pytest.raises(RuntimeError,match='outside HALO'):
        model_manager.remove_model('translation:hi','ta')
    assert (other/'keep').read_text()=='keep'


def test_nonactive_model_can_be_removed_and_reinstalled(tmp_path,monkeypatch):
    root=tmp_path/'models';root.mkdir()
    folder=root/'translate-en_hi';folder.mkdir();(folder/'model.bin').write_bytes(b'model')
    entry=model_manager.ModelEntry('translation:hi','Hindi',folder,'translation',('hi',),5)
    monkeypatch.setattr(model_manager,'MODELS',root)
    monkeypatch.setattr(model_manager,'installed_models',lambda:[entry] if folder.exists() else [])
    assert model_manager.remove_model('translation:hi','ta')==entry
    assert not folder.exists()
    with pytest.raises(RuntimeError,match='not found'):
        model_manager.remove_model('translation:hi','ta')
