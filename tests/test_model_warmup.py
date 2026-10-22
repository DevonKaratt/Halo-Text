from types import SimpleNamespace
from halo_text.pipeline import Pipeline

def test_startup_warms_selected_local_translation_engine():
 calls=[]
 p=Pipeline.__new__(Pipeline)
 p.ocr=SimpleNamespace(recognize=lambda sample:[SimpleNamespace(text='Welcome to our project.')])
 p.translator=SimpleNamespace(backend=SimpleNamespace(engine=object()),translate_many=lambda texts:calls.append(texts))
 assert p.warmup()=='Welcome to our project.'
 assert calls==[['Welcome to our project.']]

def test_startup_does_not_make_online_warmup_requests():
 p=Pipeline.__new__(Pipeline)
 p.ocr=SimpleNamespace(recognize=lambda sample:[SimpleNamespace(text='Welcome to our project.')])
 def forbidden(texts):raise AssertionError('Online startup request')
 p.translator=SimpleNamespace(backend=SimpleNamespace(session=object()),translate_many=forbidden)
 p.warmup()

def test_language_switch_does_not_make_online_warmup_request(monkeypatch):
 from halo_text.app import Worker
 from halo_text.config import Config
 config=Config(target="ta",backend="auto")
 worker=Worker(config)
 worker.pipeline=SimpleNamespace(translator=None,source_translators={},
                                 ocr=SimpleNamespace(reload_packs=lambda:None,config=config),config=config)
 def forbidden(texts):raise AssertionError("Online language switch request")
 backend=SimpleNamespace(session=object())
 monkeypatch.setattr("halo_text.translation.create_translator",
                     lambda config:SimpleNamespace(backend=backend,translate_many=forbidden))
 ready=[];worker.language_ready.connect(ready.append)
 worker.change_language(config)
 assert ready==[config]
