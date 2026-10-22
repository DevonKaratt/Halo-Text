"""Local English-to-Indian IndicTrans2 adapter; no remote Python is executed."""
import re
from .core import normalize
from .indic_setup import DIRECTORY,installed,TARGET_TAGS

class IndicTranslator:
    tags=TARGET_TAGS
    def __init__(self,config):
        if config.target not in self.tags or not installed():
            raise RuntimeError("Install the local Indian pack first: app/run.py --install-indic")
        import ctranslate2
        import sentencepiece
        from sacremoses import MosesTokenizer,MosesPunctNormalizer
        self.target=config.target
        self.tag=self.tags[config.target]
        self.normalizer=MosesPunctNormalizer(lang="en")
        self.moses=MosesTokenizer(lang="en")
        self.src=sentencepiece.SentencePieceProcessor(model_file=str(DIRECTORY/"vocab"/"model.SRC"))
        self.engine=ctranslate2.Translator(str(DIRECTORY),device="cpu",compute_type="int8",
                                          inter_threads=1,intra_threads=config.cpu_threads)

    def translate_many(self,texts):
        batches=[]
        owners=[]
        for owner,text in enumerate(texts):
            prepared=" ".join(self.moses.tokenize(self.normalizer.normalize(normalize(text)),escape=False))
            pieces=self.src.encode(prepared,out_type=str)
            for start in range(0,len(pieces),150):
                batches.append(["eng_Latn",self.tag]+pieces[start:start+150])
                owners.append(owner)
        if not batches:
            return [""]*len(texts)
        outputs=self.engine.translate_batch(batches,beam_size=2,max_batch_size=4,
                                            max_input_length=0,max_decoding_length=256)
        result=[[] for _ in texts]
        for owner,output in zip(owners,outputs):
            # Upstream target pieces are decoded in their trained shared space.
            value="".join(output.hypotheses[0]).replace("▁"," ").strip()
            value=value.replace(" ؟","؟").replace(" ۔","۔").replace(" ،","،").replace("ٮ۪","ؠ")
            value=re.sub(r"\s+([.,!?;:।])",r"\1",value)
            if self.target=="te":
                value=restore_telugu_script(value)
            elif self.target=="ta":
                value=restore_tamil_script(value)
            else:
                script_codes={"as":"as","bn":"bn","gu":"gu","kn":"kn",
                              "ml":"ml","or":"or","pa":"pa"}
                if self.target in script_codes:
                    from indicnlp.transliterate.unicode_transliterate import UnicodeIndicTransliterator
                    value=UnicodeIndicTransliterator.transliterate(value,"hi",script_codes[self.target])
                    if self.target=="or":
                        value=value.replace("ଯ଼","ୟ")
            result[owner].append(value)
        return [" ".join(parts) for parts in result]


def restore_telugu_script(text):
    """Restore the model's coordinated Indic output to Telugu Unicode.

    This adapter supports Telugu only; other scripts require their own checked
    restoration. Keep Latin text/numbers and punctuation intact.
    """
    text=text.translate(str.maketrans({"क़":"क","ख़":"ख","ग़":"ग","ज़":"ज","ड़":"ड","ढ़":"ढ","फ़":"फ","य़":"य","़":"","।":".","॥":"."}))
    return "".join(chr(ord(c)+0x300) if 0x0900<=ord(c)<=0x0963 else c for c in text)


def restore_tamil_script(text):
    """Apply the same Devanagari-to-Tamil script step used by IndicTrans2.

    The trained model emits coordinated Devanagari for Tamil. Preserve Latin
    words and numbers; punctuation is normalized by the existing adapter.
    """
    from indicnlp.transliterate.unicode_transliterate import UnicodeIndicTransliterator
    return UnicodeIndicTransliterator.transliterate(text,"hi","ta").replace("।",".")
