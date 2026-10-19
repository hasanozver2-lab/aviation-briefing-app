"""Group articles that report the same event (deterministic, no LLM). Settings: config/clustering.json."""

import html
import json
import re
from pathlib import Path

try:
    from . import source_registry, text_match
except ImportError:
    import source_registry
    import text_match


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "clustering.json"
TOKEN_PATTERN = re.compile(r"[a-z0-9]{3,}")
ENTITY_KINDS = ("groups", "carriers", "airports", "aircraft")
YEAR_RANGE = range(1900, 2100)
NUMBER_PATTERN = re.compile(r"(?<![\w.])\d{2,5}(?![\w])")
MODEL_PATTERN = re.compile(r"(?<!\w)[a-z]+-?\d[a-z0-9-]*(?!\w)")
ENTITY_NAME_FIELDS = ("name", "slug", "iata", "code", "family")


def load_clustering_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def title_tokens(title, generic):
    folded = text_match.fold(title)
    return {token for token in TOKEN_PATTERN.findall(folded) if token not in source_registry.TITLE_STOP_WORDS and token not in generic}


def entity_ids(article, config=None):
    """Strong entities only: carriers, groups, airports and specific aircraft variants (never a whole family)."""
    entities = article.get("entities") or {}
    broad = set((config or {}).get("broad_aircraft_codes", []))
    return {
        item["entity_id"] for kind in ENTITY_KINDS for item in entities.get(kind, [])
        if item.get("entity_id") and not (kind == "aircraft" and item.get("code") in broad)
    }


def _ids(article, kinds, config):
    entities = article.get("entities") or {}
    broad = set(config.get("broad_aircraft_codes", []))
    return {
        item["entity_id"] for kind in kinds for item in entities.get(kind, [])
        if item.get("entity_id") and not (kind == "aircraft" and item.get("code") in broad)
    }


def signals(article, config):
    """Distinctive facts in the title and the start of the description: numbers, model designators, engine makers."""
    text = text_match.fold(html.unescape(f"{article.get('title', '')} {str(article.get('description', ''))[:config['signal_description_chars']]}"))
    models = {token for token in MODEL_PATTERN.findall(text) if not token.isdigit()}
    # Digits that belong to a model designator (the 130 in c-130j) are not a second, independent number.
    without_models = MODEL_PATTERN.sub(" ", text)
    found = {number for number in NUMBER_PATTERN.findall(without_models) if int(number) not in YEAR_RANGE}
    found |= models
    found |= {f"maker:{maker}" for maker in config["makers"] if re.search(rf"(?<!\w){re.escape(maker)}(?!\w)", text)}
    return found


def compatible_types(left, right):
    left_type, right_type = left.get("event_type"), right.get("event_type")
    return left_type is None or right_type is None or left_type == right_type


def entity_words(article, generic):
    """Words that merely name the entities (so 'Lufthansa' or 'A350' never counts as shared evidence)."""
    entities = article.get("entities") or {}
    words = set()
    for kind in ENTITY_KINDS:
        for item in entities.get(kind, []):
            text = " ".join(str(item.get(field, "")).replace("-", " ") for field in ENTITY_NAME_FIELDS)
            words |= title_tokens(text, generic)
    return words


def is_roundup(article, config):
    folded = text_match.fold(article.get("title", ""))
    return any(term in folded for term in config["roundup_terms"])


def _shares_carrier_and_variant(left, right, config):
    carriers = _ids(left, ("carriers", "groups"), config) & _ids(right, ("carriers", "groups"), config)
    variants = _ids(left, ("aircraft",), config) & _ids(right, ("aircraft",), config)
    return bool(carriers and variants)


def _shares_distinctive_signals(left, right, config):
    shared = signals(left, config) & signals(right, config)
    has_number = any(item.isdigit() for item in shared)
    has_model_or_maker = any(not item.isdigit() for item in shared)
    return len(shared) >= config["min_shared_signals"] and has_number and has_model_or_maker


def same_story(left, right, config):
    window = config["window_hours"] * 3600
    if abs(left.get("timestamp", 0) - right.get("timestamp", 0)) > window:
        return False
    if source_registry.title_similarity(left.get("title", ""), right.get("title", "")) >= config["title_similarity"]:
        return True
    if is_roundup(left, config) or is_roundup(right, config):
        return False
    if compatible_types(left, right) and _shares_carrier_and_variant(left, right, config):
        return True
    if compatible_types(left, right) and _shares_distinctive_signals(left, right, config):
        return True
    if not (entity_ids(left, config) & entity_ids(right, config)):
        return False
    generic = set(config["generic_tokens"])
    own_words = entity_words(left, generic) | entity_words(right, generic)
    shared = (title_tokens(left.get("title", ""), generic) - own_words) & (title_tokens(right.get("title", ""), generic) - own_words)
    distinctive = [token for token in shared if any(char.isdigit() for char in token) or len(token) >= config["distinctive_min_length"]]
    return len(shared) >= config["min_shared_tokens"] and len(distinctive) >= config["min_distinctive_tokens"]


def cluster_articles(articles, config=None):
    """Lists of article indexes, one list per story, in order of first appearance."""
    config = config or load_clustering_config()
    parent = list(range(len(articles)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for i in range(len(articles)):
        for j in range(i + 1, len(articles)):
            if same_story(articles[i], articles[j], config):
                parent[find(i)] = find(j)
    groups = {}
    for index in range(len(articles)):
        groups.setdefault(find(index), []).append(index)
    return sorted(groups.values(), key=lambda indexes: indexes[0])
