"""Group articles that report the same event (deterministic, no LLM). Settings: config/clustering.json."""

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
ENTITY_NAME_FIELDS = ("name", "slug", "iata", "code", "family")


def load_clustering_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def title_tokens(title, generic):
    folded = text_match.fold(title)
    return {token for token in TOKEN_PATTERN.findall(folded) if token not in source_registry.TITLE_STOP_WORDS and token not in generic}


def entity_ids(article):
    entities = article.get("entities") or {}
    return {item["entity_id"] for kind in ENTITY_KINDS for item in entities.get(kind, []) if item.get("entity_id")}


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


def same_story(left, right, config):
    window = config["window_hours"] * 3600
    if abs(left.get("timestamp", 0) - right.get("timestamp", 0)) > window:
        return False
    if source_registry.title_similarity(left.get("title", ""), right.get("title", "")) >= config["title_similarity"]:
        return True
    if is_roundup(left, config) or is_roundup(right, config) or not (entity_ids(left) & entity_ids(right)):
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
