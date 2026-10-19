"""Recover legacy headlines using collected publisher evidence; never fetch search pages or call a model."""

import copy
import json
import re
from pathlib import Path
from urllib.parse import urlparse

try:
    from . import source_catalog, source_registry, story_lifecycle, text_match
except ImportError:
    import source_catalog
    import source_registry
    import story_lifecycle
    import text_match


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "source_recovery.json"


def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def source_is_blocked(name, rows, config):
    canonical = config["publisher_aliases"].get(name, name)
    row = next((row for row in rows if row["name"] == canonical), None)
    return bool(row and (row.get("status") == "excluded_policy" or row.get("license_status") == "paid"
                         or source_catalog.notes_of(row).get("license_required")))


def approved_direct_candidate(candidate, rows):
    original = candidate.get("original_source") or {}
    url = original.get("url", "")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not original.get("title"):
        return False
    domain = source_catalog.registrable_key(url)
    return any(source_catalog.registrable_key(row["url"]) == domain and row.get("active") == "1"
               and row.get("status") == "active" and row.get("license_status") == "public"
               and not source_catalog.notes_of(row).get("license_required") for row in rows)


def publisher_titles(story):
    titles = [(story.get("original_source") or {}).get("title", "")]
    titles.extend(source.get("title", "") for source in story.get("sources", []))
    return [title for title in titles if title]


def matches_story(legacy, candidate, config):
    left_time = story_lifecycle.parse_iso(legacy.get("published_at_iso"))
    right_time = story_lifecycle.parse_iso(candidate.get("published_at_iso"))
    if not right_time:
        return False
    if left_time and abs((left_time - right_time).total_seconds()) > config["max_publication_gap_hours"] * 3600:
        return False
    for left in publisher_titles(legacy):
        for right in publisher_titles(candidate):
            # A near-identical headline with a conflicting order quantity is a different claim.
            left_numbers = set(re.findall(r"\d+", text_match.fold(left)))
            right_numbers = set(re.findall(r"\d+", text_match.fold(right)))
            if left_numbers and right_numbers and left_numbers != right_numbers:
                continue
            if source_registry.title_similarity(left, right) >= config["min_title_similarity"]:
                return True
    return False


def reconcile_day(day, candidates, now, config=None):
    """Return a repaired COPY and a count. Existing ids/history survive, unsupported model prose does not."""
    if not day or not candidates:
        return day, 0
    config = config or load_config()
    rows = source_catalog.read_rows()
    selection = story_lifecycle.load_relevance_config()["selection"]
    verified = [candidate for candidate in candidates if approved_direct_candidate(candidate, rows)]
    result = copy.deepcopy(day)
    repaired = 0
    for index, legacy in enumerate(result.get("stories", [])):
        if not story_lifecycle.has_only_unverified_sources(legacy, selection):
            continue
        match = next((candidate for candidate in verified if matches_story(legacy, candidate, config)), None)
        if match is None:
            continue
        recovered = copy.deepcopy(match)
        # A recovered story uses the directly collected headline until a new narrative is generated.
        recovered["headline"] = recovered["original_source"]["title"]
        for field in story_lifecycle.NARRATIVE_FIELDS:
            if field != "headline":
                recovered.pop(field, None)
        recovered.update(story_id=legacy["story_id"], id=legacy["story_id"],
                         first_seen_at=legacy.get("first_seen_at") or story_lifecycle.to_iso(now),
                         last_updated_at=story_lifecycle.to_iso(now), update_reasons=["source_verified"],
                         narrative_status="pending", source_verification_status="verified")
        result["stories"][index] = recovered
        repaired += 1
    return result, repaired


def pending_titles(day, date_text=None):
    """Metadata-only waiting area: no LLM narrative, ranking, badges, or unverified external links."""
    config = load_config()
    rows = source_catalog.read_rows()
    relevance = story_lifecycle.load_relevance_config()
    badges = story_lifecycle.load_badges_config()
    pending = []
    for story in day.get("stories", []):
        if not story_lifecycle.has_only_unverified_sources(story, relevance["selection"]):
            continue
        original = story.get("original_source") or {}
        title, name = original.get("title", ""), original.get("source_name", "")
        if not title or source_is_blocked(name, rows, config):
            continue
        if date_text and not story_lifecycle.published_on_day(story, date_text, badges):
            continue
        minimal = {"headline": title, "event_type": story.get("event_type"), "original_source": original}
        if story_lifecycle.is_military_story(minimal, relevance["selection"]) or story_lifecycle.is_ground_traffic_story(minimal, relevance["selection"]):
            continue
        commentary = relevance.get("commentary") or {}
        if text_match.TermSet(commentary.get("title_patterns", [])).any(title) or story_lifecycle.is_finance_commentary(minimal, commentary):
            continue
        pending.append({"story_id": story.get("story_id", ""), "headline": title,
                        "reported_source": name, "language": story.get("language", "en"),
                        "source_verification_status": "pending"})
    return pending[:config["max_pending_titles"]]
