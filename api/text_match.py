"""Boundary-safe, Turkish-aware term matching shared by entity and event classification."""

import re
import unicodedata
from collections import namedtuple


APOSTROPHES = "'’ʼ`´"
STEM_MARK = "*"
CASE_SENSITIVE_MARK = "="
MAX_ACRONYM_LENGTH = 4
# Python's default casing maps I->i and İ->i̇ (i + combining dot), which is wrong for Turkish.
TURKISH_CASE_MAP = {ord("İ"): "i", ord("I"): "ı"}
APOSTROPHE_PATTERN = re.compile(f"[{re.escape(APOSTROPHES)}]")

Prepared = namedtuple("Prepared", ["raw", "folded"])


def turkish_lower(text):
    return str(text or "").translate(TURKISH_CASE_MAP).lower()


def normalize_apostrophes(text):
    return APOSTROPHE_PATTERN.sub("'", str(text or ""))


def _fold_char(char):
    """Map one character to its unaccented ASCII base, keeping string length unchanged."""
    if char.isascii():
        return char
    base = unicodedata.normalize("NFKD", char)
    if len(base) > 1 and base[0].isascii() and all(unicodedata.combining(extra) for extra in base[1:]):
        return base[0]
    return char


def fold(text):
    """Canonical matching form: Turkish-correct lowercase without diacritics or dotless i.

    Folding makes "HAVALİMANI", "havalimanı" and "HAVALIMANI" identical, which is what a
    headline matcher wants even though they are different words to a Turkish speller.
    Length is preserved so match positions line up with the raw text.
    """
    lowered = normalize_apostrophes(turkish_lower(text)).replace("ı", "i")
    return "".join(_fold_char(char) for char in lowered)


def prepare(text):
    if isinstance(text, Prepared):
        return text
    raw = normalize_apostrophes(text)
    return Prepared(raw=raw, folded=fold(raw))


def is_case_sensitive_acronym(term):
    """Short all-caps terms (SAF, ASK, SAS, ANA) collide with ordinary words when lowercased.

    A leading "=" forces case sensitivity for longer names such as "=SWISS".
    """
    if term.startswith(CASE_SENSITIVE_MARK):
        return True
    stem = term.rstrip(STEM_MARK).strip()
    return stem.isascii() and stem.isalpha() and stem.isupper() and len(stem) <= MAX_ACRONYM_LENGTH


def compile_term(term, allow_plural=False):
    """Return (regex, is_acronym).

    Default is a whole-word match that tolerates an apostrophe suffix (THY'nin, Delta's).
    A trailing "*" turns the term into a word-prefix stem for agglutinative Turkish forms.
    """
    raw = str(term).strip()
    acronym = is_case_sensitive_acronym(raw)
    is_stem = raw.endswith(STEM_MARK)
    body = normalize_apostrophes(raw.lstrip(CASE_SENSITIVE_MARK).rstrip(STEM_MARK).strip())
    key = body if acronym else fold(body)
    pattern = r"\s+".join(re.escape(part) for part in key.split())
    if not pattern:
        raise ValueError(f"empty match term: {term!r}")
    if is_stem:
        tail = r"\w*"
    else:
        plural = r"(?:s|es)?" if allow_plural and not acronym else ""
        tail = rf"{plural}(?:'\w+)?"
    return re.compile(rf"(?<!\w){pattern}{tail}(?!\w)"), acronym


class TermSet:
    """A list of terms compiled once and matched against prepared text."""

    def __init__(self, terms, allow_plural=False):
        self._entries = [(term, *compile_term(term, allow_plural)) for term in terms]

    @property
    def terms(self):
        return [term for term, _, _ in self._entries]

    def spans(self, text):
        """Return [(term, start, end)] for every occurrence of every term."""
        prepared = prepare(text)
        found = []
        for term, regex, acronym in self._entries:
            for match in regex.finditer(prepared.raw if acronym else prepared.folded):
                found.append((term, match.start(), match.end()))
        return found

    def matches(self, text):
        """Return [(term, first_position)] for every term present in the text."""
        first = {}
        for term, start, _ in self.spans(text):
            first.setdefault(term, start)
        return list(first.items())

    def count(self, text):
        return len(self.matches(text))

    def any(self, text):
        return bool(self.matches(text))
