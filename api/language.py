"""Deterministic language rules: which language an article or a story is in, and which language its narrative is written in.

No LLM is involved. Rules and word lists live in config/language.json; per-source languages in config/sources.csv.
"""

import csv
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LANGUAGE_CONFIG_PATH = BASE_DIR / "config" / "language.json"
SOURCES_CSV_PATH = BASE_DIR / "config" / "sources.csv"
WORD_PATTERN = re.compile(r"[^\W\d_]+", re.UNICODE)


def load_language_config():
    return json.loads(LANGUAGE_CONFIG_PATH.read_text(encoding="utf-8"))


def source_languages():
    """{source name: language} from config/sources.csv; rows without a language are left out."""
    with SOURCES_CSV_PATH.open(encoding="utf-8-sig", newline="") as csv_file:
        return {row["name"]: row["language"].strip().lower() for row in csv.DictReader(csv_file) if row.get("language", "").strip()}


def turkish_lower(text):
    """str.lower() turns İ into 'i̇' (i + combining dot) and I into i; Turkish needs İ→i and I→ı."""
    return str(text).replace("İ", "i").replace("I", "ı").lower()


def detect_language(text, config=None):
    """'tr' or the default language, from Turkish-only letters and common Turkish words."""
    config = config or load_language_config()
    detection = config["detection"]
    text = str(text or "")
    words = WORD_PATTERN.findall(turkish_lower(text))
    turkish_words = set(detection["words"])
    word_hits = sum(1 for word in words if word in turkish_words)
    has_turkish_letter = any(letter in text for letter in detection["turkish_only_letters"])
    is_turkish = (has_turkish_letter and word_hits >= 1) or word_hits >= detection["min_word_hits"]
    return config["story_rule"]["turkish_only_language"] if is_turkish else config["default_language"]


def article_language(source_name, text="", config=None, known=None):
    """The source's language from sources.csv; the text is inspected only when the source has none."""
    config = config or load_language_config()
    known = source_languages() if known is None else known
    return known.get(str(source_name or "")) or detect_language(text, config)


def story_language_from(languages, config=None):
    """Turkish only when every source language is Turkish; an empty, mixed or English set is English."""
    config = config or load_language_config()
    rule = config["story_rule"]
    languages = [language for language in languages if language]
    all_turkish = bool(languages) and all(language == rule["turkish_only_language"] for language in languages)
    return rule["turkish_only_language"] if all_turkish else rule["otherwise"]


def story_language(story, config=None):
    """Language of a story, from its sources. Sources stored before languages were recorded are looked up by
    name in sources.csv and, failing that, detected from their titles."""
    config = config or load_language_config()
    known = source_languages()
    entries = story.get("sources") or []
    if not entries:
        source = story.get("original_source") or {}
        entries = [{"name": source.get("source_name"), "title": source.get("title") or story.get("headline", "")}]
    languages = [entry.get("language") or article_language(entry.get("name"), entry.get("title", ""), config, known) for entry in entries]
    return story_language_from(languages, config)
