"""Spelling backend: SymSpell (symspellpy, MIT) + scientific-vocabulary
guards.

Why guards matter (measured before building): a general English frequency
dictionary doesn't know 'seroprevalence', 'covariates', or 'nowcasting' —
flagging the researcher's own terminology is exactly the false-positive
fatigue that kills checkers. Layers of defence:

1. built-in frequency dictionary (~83k words)
2. shipped scientific lexicon (data/scientific_terms.txt — epi/stats/
   modelling vocabulary)
3. the user's personal dictionary (~/.researchly/dictionary.txt and
   [dictionary] words=[...] in .researchly.toml) — `researchly dict add X`
4. morphological fallback (covariates → covariate, behaviours → behaviour)
5. UK/US variant mapping (modelling/modeling, behaviour/behavior, -ise/-ize)
6. document-learned terms: a word used 3+ times is the author's vocabulary
"""

from __future__ import annotations

import re

import threading
from pathlib import Path

_LOCK = threading.Lock()
_SYM = None
_DOMAIN: set[str] | None = None

USER_DICT_FILE = Path.home() / ".researchly" / "dictionary.txt"

SUFFIXES = ("es", "s", "ed", "d", "ing", "ly", "er", "est")

# Closed-class words never take suffixes — "thiss" is a typo, not "this+s".
# Without this, the morphological fallback would excuse doubled-letter typos
# of function words.
FUNCTION_WORDS = frozenset("""
this that these those the and but or nor if is was are were be been being
has have had with from for not of to in on at by it its as we you they he
she him her them his our your their than then when which who whom whose
what why how would could should will shall may might must do does did done
am us me my mine no so too very can cannot into onto upon about above below
over under again further once here there all any both each few more most
other some such only own same
""".split())


def get_sym():
    """Lazy singleton SymSpell with the bundled English dictionary."""
    global _SYM
    with _LOCK:
        if _SYM is None:
            from symspellpy import SymSpell
            import importlib.resources as ir
            sym = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
            ref = (ir.files("symspellpy")
                   / "frequency_dictionary_en_82_765.txt")
            with ir.as_file(ref) as p:
                sym.load_dictionary(str(p), 0, 1)
            _SYM = sym
    return _SYM


def domain_terms() -> set[str]:
    global _DOMAIN
    if _DOMAIN is None:
        terms: set[str] = set()
        data = Path(__file__).parent / "data" / "scientific_terms.txt"
        if data.exists():
            for line in data.read_text(encoding="utf-8").splitlines():
                line = line.strip().lower()
                if line and not line.startswith("#"):
                    terms.add(line)
        _DOMAIN = terms
    return _DOMAIN


def user_dictionary(extra: list[str] | None = None) -> set[str]:
    words: set[str] = set(w.lower() for w in (extra or []))
    try:
        if USER_DICT_FILE.exists():
            for line in USER_DICT_FILE.read_text(
                    encoding="utf-8").splitlines():
                line = line.strip().lower()
                if line:
                    words.add(line)
    except Exception:
        pass
    return words


def add_to_user_dictionary(word: str) -> bool:
    try:
        USER_DICT_FILE.parent.mkdir(exist_ok=True)
        existing = user_dictionary()
        if word.lower() in existing:
            return True
        with open(USER_DICT_FILE, "a", encoding="utf-8") as f:
            f.write(word.lower() + "\n")
        return True
    except Exception:
        return False


def is_known(word: str) -> bool:
    """Exact dictionary membership (distance-0 lookup)."""
    from symspellpy import Verbosity
    hits = get_sym().lookup(word, Verbosity.TOP, max_edit_distance=0,
                            include_unknown=False)
    return bool(hits)


def _variants(word: str) -> list[str]:
    """UK↔US spelling transforms, tried both directions."""
    pairs = (("isation", "ization"), ("ise", "ize"), ("ised", "ized"),
             ("ising", "izing"), ("yse", "yze"), ("ysed", "yzed"),
             ("ysing", "yzing"), ("yser", "yzer"),
             ("our", "or"), ("lling", "ling"), ("lled", "led"),
             ("ller", "ler"), ("ogue", "og"), ("aemia", "emia"),
             ("oea", "ea"), ("tre", "ter"))
    out = []
    for a, b in pairs:
        if a in word:
            out.append(word.replace(a, b))
        if b in word:
            out.append(word.replace(b, a))
    return out


# Prefixes that make a real word from a real word: "unstratified",
# "uncited", "autoregression", "nonzero". A typo in the stem still fails,
# because the stem itself must be known.
DERIVATIONAL_PREFIXES = ("non", "un", "mis", "re", "pre", "post", "over",
                         "under", "sub", "co", "multi", "inter", "intra",
                         "semi", "pseudo", "quasi", "auto", "hyper", "hypo",
                         "anti", "counter", "cross", "self")


def _known_stem(word: str) -> bool:
    """A stem behind a prefix must be a dictionary word as written (or its
    UK/US twin). No suffix-stripping here: "mis" + "peled" would pass as
    "pele" + "d", and "mispeled" is the classic typo this tier exists for."""
    return is_known(word) or any(is_known(v) for v in _variants(word))


def known_with_fallbacks(word: str) -> bool:
    """Known directly, morphologically, as a UK/US variant, or as a known
    word behind a common prefix."""
    if is_known(word):
        return True
    # "crosssectional": a tripled letter is a lost hyphen or a slip, not a
    # prefixed word, however real the stem.
    tripled = re.search(r"(.)\1\1", word) is not None
    for p in () if tripled else DERIVATIONAL_PREFIXES:
        if word.startswith(p) and len(word) - len(p) >= 4 \
                and _known_stem(word[len(p):]):
            return True
    for suf in SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            base = word[: -len(suf)]
            if base not in FUNCTION_WORDS and is_known(base):
                return True
    for v in _variants(word):
        if is_known(v):
            return True
        for suf in SUFFIXES:
            if v.endswith(suf) and len(v) - len(suf) >= 3 \
                    and is_known(v[: -len(suf)]):
                return True
    return False


def suggest(word: str, top_n: int = 3) -> list[str]:
    return [t for t, _ in suggest_with_distance(word, top_n)]


def suggest_with_distance(word: str, top_n: int = 3) -> list[tuple[str, int]]:
    from symspellpy import Verbosity
    hits = get_sym().lookup(word, Verbosity.CLOSEST, max_edit_distance=2,
                            include_unknown=False,
                            transfer_casing=False)
    out: list[tuple[str, int]] = []
    for h in hits:
        if h.term != word and all(h.term != t for t, _ in out):
            out.append((h.term, h.distance))
        if len(out) >= top_n:
            break
    return out


def match_case(suggestion: str, original: str) -> str:
    if original[:1].isupper():
        return suggestion[:1].upper() + suggestion[1:]
    return suggestion
