"""Languages a session may request: BCP-47 whose primary subtag is a real language.

There is no per-provider language list in the STT config (`by_language` is an override map), so
the API checks the primary subtag against ISO 639-1 plus the three-letter codes Chirp 3 uses
(`fil`, `yue`). Whether the chosen STT model handles it is the provider's call; this only
rejects typos and non-languages at create time instead of at transcription.
"""

import re

_BCP47 = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}$")

PRIMARY_LANGUAGES = frozenset(
    "aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy "
    "da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu "
    "hy hz ia id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb "
    "lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om "
    "or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw "
    "ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu "
    "fil yue".split()
)


def is_supported_language(tag: str) -> bool:
    return tag == "auto" or (
        bool(_BCP47.match(tag)) and tag.split("-", 1)[0].lower() in PRIMARY_LANGUAGES
    )
