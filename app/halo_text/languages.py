"""22 scheduled Indian output languages followed by 30 widely spoken global targets."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Language:
    code: str
    name: str
    font: str
    sample: str
    group: str = "Global"
    rtl: bool = False

INDIAN_DATA="""as|Assamese|Nirmala UI|অসমীয়া
bn|Bengali|Nirmala UI|বাংলা
brx|Bodo|Nirmala UI|बड़ो
doi|Dogri|Nirmala UI|डोगरी
gu|Gujarati|Nirmala UI|ગુજરાતી
hi|Hindi|Nirmala UI|हिन्दी
kn|Kannada|Nirmala UI|ಕನ್ನಡ
ks|Kashmiri|Segoe UI|کٲشُر
gom|Konkani|Nirmala UI|कोंकणी
mai|Maithili|Nirmala UI|मैथिली
ml|Malayalam|Nirmala UI|മലയാളം
mni-Mtei|Manipuri (Meitei)|Noto Sans Meetei Mayek|ꯃꯤꯇꯩ
mr|Marathi|Nirmala UI|मराठी
ne|Nepali|Nirmala UI|नेपाली
or|Odia|Nirmala UI|ଓଡ଼ିଆ
pa|Punjabi|Nirmala UI|ਪੰਜਾਬੀ
sa|Sanskrit|Nirmala UI|संस्कृतम्
sat|Santali (Ol Chiki)|Noto Sans Ol Chiki|ᱥᱟᱱᱛᱟᱲᱤ
sd|Sindhi|Segoe UI|سنڌي
ta|Tamil|Nirmala UI|தமிழ்
te|Telugu|Nirmala UI|తెలుగు
ur|Urdu|Segoe UI|اردو"""
GLOBAL_DATA="""en|English|Segoe UI|English
zh-CN|Chinese (Mandarin)|Noto Sans SC|中文
es|Spanish|Segoe UI|Español
ar|Arabic|Segoe UI|العربية
fr|French|Segoe UI|Français
pt|Portuguese|Segoe UI|Português
id|Indonesian|Segoe UI|Indonesia
ru|Russian|Segoe UI|Русский
de|German|Segoe UI|Deutsch
ja|Japanese|Yu Gothic|日本語
vi|Vietnamese|Segoe UI|Tiếng Việt
sw|Swahili|Segoe UI|Kiswahili
ha|Hausa|Segoe UI|Hausa
tr|Turkish|Segoe UI|Türkçe
tl|Filipino (Tagalog)|Segoe UI|Tagalog
yue|Chinese (Cantonese)|Noto Sans SC|粵語
fa|Persian|Segoe UI|فارسی
ko|Korean|Malgun Gothic|한국어
am|Amharic|Ebrima|አማርኛ
th|Thai|Leelawadee UI|ภาษาไทย
jv|Javanese|Segoe UI|Jawa
it|Italian|Segoe UI|Italiano
yo|Yoruba|Segoe UI|Yorùbá
my|Burmese|Myanmar Text|မြန်မာ
ps|Pashto|Segoe UI|پښتو
uz|Uzbek|Segoe UI|Oʻzbek
ms|Malay|Segoe UI|Melayu
ig|Igbo|Segoe UI|Igbo
om|Oromo|Segoe UI|Oromoo
pl|Polish|Segoe UI|Polski
uk|Ukrainian|Segoe UI|Українська"""
LANGUAGES={}
for group,data in (("Indian",INDIAN_DATA),("Global",GLOBAL_DATA)):
    for row in data.splitlines():
        code,name,font,sample=row.split("|")
        LANGUAGES[code]=Language(code,name,font,sample,group,code in {"ks","sd","ur","ar","fa","ps"})

def language(code):
    try:
        return LANGUAGES[code]
    except (KeyError,TypeError):
        raise ValueError("Unknown target language: "+str(code)) from None
