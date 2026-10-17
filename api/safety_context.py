"""Airline context for safety incidents.

safety_incident carries the highest event weight (0.95) and is meant for passenger-airline events. A general-aviation accident or a
crash with no airline, airport or passenger context must not borrow that weight: after the entities are annotated, such an article
loses the type (its story stays in the list, untyped, scored the normal way). No weight or threshold is touched.
"""

import json
from pathlib import Path

try:
    from . import text_match
except ImportError:
    import text_match

TAXONOMY_PATH = Path(__file__).resolve().parent.parent / "config" / "event_taxonomy.json"


def load_config():
    return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))["safety_context"]


def _has_entity(article, kinds):
    entities = article.get("entities") or {}
    return any(entities.get(kind) for kind in kinds)


def classify_context(article, config):
    """('strong' | 'weak' | 'none', is_general_aviation) for one article."""
    text = text_match.prepare(f"{article.get('title', '')} {article.get('description', '')}")
    general_aviation = text_match.TermSet(config["general_aviation_terms"]).any(text)
    strong = _has_entity(article, config["strong_context_entities"]) or text_match.TermSet(config["strong_context_terms"]).any(text)
    weak = _has_entity(article, config["weak_context_entities"]) or text_match.TermSet(config["weak_context_terms"]).any(text)
    return ("strong" if strong else "weak" if weak else "none"), general_aviation


def keeps_safety_type(article, config):
    context, general_aviation = classify_context(article, config)
    if context == "strong":
        return True
    return context == "weak" and not general_aviation


def enforce(articles, config=None):
    """Drop the safety type from articles without an airline context. Returns how many were changed."""
    config = config or load_config()
    changed = 0
    for article in articles:
        if article.get("event_type") in config["applies_to"] and not keeps_safety_type(article, config):
            article["context_demoted_from"] = article["event_type"]
            article["event_type"], article["event_weight"] = None, None
            changed += 1
    return changed
