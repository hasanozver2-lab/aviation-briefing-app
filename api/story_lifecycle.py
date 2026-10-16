"""Story lifecycle: relevance score, stable identity, daily archive, badges and ordering.

Everything here is deterministic and rule based (no LLM). Thresholds and durations come
from config/badges.json and config/relevance.json, read at use time.
"""

import copy
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from . import clustering, source_registry, text_match
    from .urls import canonicalize_url
except ImportError:
    import clustering
    import source_registry
    import text_match
    from urls import canonicalize_url


BASE_DIR = Path(__file__).resolve().parent.parent
BADGES_CONFIG_PATH = BASE_DIR / "config" / "badges.json"
RELEVANCE_CONFIG_PATH = BASE_DIR / "config" / "relevance.json"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BADGE_NEW, BADGE_UPDATED, BADGE_BREAKING = "new", "updated", "breaking"
# Not part of the change fingerprint: they differ on every run without meaning anything.
VOLATILE_DAY_KEYS = {"generated_at", "time_str", "last_pipeline_run_at", "last_pipeline_attempt_at", "heading", "warning", "market", "badges"}
VOLATILE_STORY_KEYS = {"badges"}
HEAD_KEYS_TO_DROP = {"stories"}
# The LLM-written part of a story. It is kept when a story is refreshed, and regenerated only after
# a material update (narrative_status goes back to "pending" until then).
NARRATIVE_FIELDS = (
    "headline", "lead", "detailed_analysis", "data_points", "strategic_impact", "market_exposure",
    "why_it_matters", "thy_impact_assessment", "related_news", "narrative_generated_at",
)
NARRATIVE_PENDING = "pending"


def load_badges_config():
    return json.loads(BADGES_CONFIG_PATH.read_text(encoding="utf-8"))


def load_relevance_config(version=None):
    """The scoring config of one version (default: active_version); old versions stay loadable."""
    raw = json.loads(RELEVANCE_CONFIG_PATH.read_text(encoding="utf-8"))
    name = version or raw["active_version"]
    return {**raw["versions"][name], "version": name}


# --- time ---------------------------------------------------------------------

def utc_now():
    return datetime.now(timezone.utc)


def to_iso(moment):
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value):
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def local_timezone(config):
    """The configured zone; a fixed offset when the system has no tz database (e.g. Windows)."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(config["timezone"])
    except Exception:  # ZoneInfoNotFoundError, ImportError
        return timezone(timedelta(hours=config["fallback_utc_offset_hours"]))


def day_key(moment, config):
    return moment.astimezone(local_timezone(config)).date().isoformat()


def previous_day_key(date_text):
    return (date.fromisoformat(date_text) - timedelta(days=1)).isoformat()


def validate_date(value):
    """YYYY-MM-DD for a real calendar day, else ValueError."""
    if not isinstance(value, str) or not DATE_PATTERN.match(value):
        raise ValueError("date must be YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must be a real calendar day") from exc
    return value


# --- relevance score --------------------------------------------------------------

def _source_facts(item):
    """(official, tier) for an article or a story."""
    source = item.get("original_source") or item
    return bool(source.get("official")), source.get("tier")


def is_finance_commentary(item, commentary):
    """Stock and price-target commentary, or financial news that is neither official nor from a trusted tier.

    Company results from an airline's own channel or a tier 1-2 outlet are real news and stay.
    """
    if not commentary:
        return False
    title = item.get("headline") or item.get("title") or ""
    official, tier = _source_facts(item)
    trusted = official or (tier is not None and int(tier) <= commentary["trusted_max_tier"])
    if trusted:
        return False
    if text_match.TermSet(commentary["title_patterns"]).any(title):
        return True
    return item.get("event_type") in commentary["finance_event_types"]


def best_tier(entities):
    """Most prominent (lowest) tier among the matched groups, carriers and airports."""
    tiers = [
        item.get("tier")
        for kind in ("groups", "carriers", "airports")
        for item in (entities or {}).get(kind, [])
        if item.get("tier")
    ]
    return min(tiers) if tiers else None


def score_article(article, source_count, config=None):
    """Return (score 0-100, components 0-1). Pure function of the article's own data."""
    config = config or load_relevance_config()
    weights = config["weights"]
    event_weight = article.get("event_weight")
    reliability = article.get("reliability_weight")
    tier = best_tier(article.get("entities"))
    full_at = max(2, int(config["corroboration_full_at_sources"]))
    components = {
        "event_type": float(config["event_type_default"] if event_weight is None else event_weight),
        "source_reliability": float(config["reliability_default"] if reliability is None else reliability),
        "entity_prominence": float(config["tier_prominence"].get(str(tier), 0.0)) if tier else 0.0,
        "official_source": 1.0 if article.get("official") else 0.0,
        "corroboration": min(1.0, max(0, source_count - 1) / (full_at - 1)),
    }
    score = sum(weights[name] * value for name, value in components.items())
    commentary = config.get("commentary")
    if is_finance_commentary(article, commentary):
        score *= commentary["score_multiplier"]
    return round(score, 1), {name: round(value, 3) for name, value in components.items()}


def _source_entry(article):
    return {"name": str(article.get("source", "")), "url": str(article.get("link", "")), "title": str(article.get("title", ""))}


def enrich_stories(stories, articles, relevance_config=None):
    """Add story_id, relevance score, the publishers covering the story and its publication time."""
    config = relevance_config or load_relevance_config()
    index_by_url = {canonicalize_url(article.get("link")): index for index, article in enumerate(articles)}
    cluster_by_index = {}
    for indexes in clustering.cluster_articles(articles):
        for index in indexes:
            cluster_by_index[index] = indexes

    for story in stories:
        source = story.get("original_source") or {}
        index = index_by_url.get(canonicalize_url(source.get("url")))
        if index is None:
            article = {}
            sources = [{"name": str(source.get("source_name", "")), "url": str(source.get("url", "")), "title": str(source.get("title", ""))}]
        else:
            article = articles[index]
            members = [articles[i] for i in cluster_by_index.get(index, [index])]
            sources, seen = [], set()
            for member in sorted(members, key=lambda item: (item.get("timestamp", 0), item.get("link", ""))):
                canonical = canonicalize_url(member.get("link"))
                if canonical and canonical not in seen:
                    seen.add(canonical)
                    sources.append(_source_entry(member))
        publishers = {entry["name"] for entry in sources if entry["name"]}
        score, components = score_article(article, max(1, len(publishers)), config)
        published = article.get("timestamp")
        story.update({
            "story_id": story.get("id") or stable_story_id(source.get("url"), story.get("headline")),
            "relevance_score": score,
            "score_components": components,
            "sources": sources,
            "source_count": max(1, len(publishers)),
            "published_at_iso": to_iso(datetime.fromtimestamp(published, tz=timezone.utc)) if isinstance(published, (int, float)) else "",
        })
    return stories


def cluster_representatives(articles):
    """One article per group of near-identical titles: the most reliable source, earliest among equals."""
    representatives = []
    for indexes in clustering.cluster_articles(articles):
        members = [articles[index] for index in indexes]
        representatives.append(max(members, key=lambda a: (a.get("reliability_weight") or 0, bool(a.get("official")), -a.get("timestamp", 0))))
    return representatives


def is_military_story(story, selection):
    """Defence/military items that do not involve any airline or civil aviation context are out of scope."""
    exclude_terms = selection.get("exclude_terms")
    if not exclude_terms:
        return False
    title = story.get("headline", "")
    if not text_match.TermSet(exclude_terms).any(title) or text_match.TermSet(selection.get("keep_terms", [])).any(title):
        return False
    entities = story.get("entities") or {}
    return not (entities.get("carriers") or entities.get("groups"))


def select_stories(stories, selection, commentary=None):
    """Stories to archive: the listed ones (score >= min_score, at most max_per_run) and the archive-only low band
    (archive_min_score <= score < min_score, at most max_low_per_run). Military items and finance commentary are dropped."""
    archive_minimum = selection.get("archive_min_score", selection["min_score"])
    eligible = [
        story for story in stories
        if float(story.get("relevance_score", 0)) >= archive_minimum and not is_military_story(story, selection)
        and not (selection.get("exclude_commentary") and is_finance_commentary(story, commentary))
    ]
    eligible.sort(key=lambda story: (-float(story["relevance_score"]), story["story_id"]))
    listed = [story for story in eligible if float(story["relevance_score"]) >= selection["min_score"]][: selection["max_per_run"]]
    low = [story for story in eligible if float(story["relevance_score"]) < selection["min_score"]][: selection.get("max_low_per_run", selection["max_per_run"])]
    return listed + low


def stable_story_id(source_url, headline=""):
    """A hash of the canonical source URL, so the same story keeps its id across runs and days."""
    identity = canonicalize_url(source_url) or str(headline or "").strip().lower()
    return f"story-{hashlib.sha1(identity.encode('utf-8')).hexdigest()[:12]}"


# --- matching and merging -----------------------------------------------------------

def _story_urls(story):
    urls = {canonicalize_url(entry.get("url")) for entry in story.get("sources", [])}
    urls.add(canonicalize_url((story.get("original_source") or {}).get("url")))
    urls.discard("")
    return urls


def _story_titles(story):
    titles = [story.get("headline", ""), (story.get("original_source") or {}).get("title", "")]
    titles.extend(entry.get("title", "") for entry in story.get("sources", []))
    return [title for title in titles if title]


def find_match(story, candidates, threshold):
    """The stored story this one continues: same id, a shared source URL, or a near-identical title."""
    candidates = list(candidates)
    for candidate in candidates:
        if candidate.get("story_id") == story.get("story_id"):
            return candidate
    urls = _story_urls(story)
    for candidate in candidates:
        if urls & _story_urls(candidate):
            return candidate
    best, best_similarity = None, 0.0
    for candidate in candidates:
        for title in _story_titles(story):
            for other in _story_titles(candidate):
                similarity = source_registry.title_similarity(title, other)
                if similarity > best_similarity:
                    best, best_similarity = candidate, similarity
    return best if best_similarity >= threshold else None


def _is_same_story(story, candidate, threshold):
    if candidate.get("story_id") == story.get("story_id") or _story_urls(story) & _story_urls(candidate):
        return True
    return any(
        source_registry.title_similarity(title, other) >= threshold
        for title in _story_titles(story) for other in _story_titles(candidate)
    )


def _consolidate(stored, story, threshold):
    """The stored story an incoming one belongs to. Several stored stories that turn out to be the same
    event (they were archived before they could be clustered) are folded into the oldest one: its
    first_seen_at and narrative stay, no source is lost, only the duplicate entries disappear."""
    matches = [candidate for candidate in stored if _is_same_story(story, candidate, threshold)]
    if not matches:
        return None
    primary = min(matches, key=lambda item: (item.get("first_seen_at", ""), item.get("story_id", "")))
    for other in matches:
        if other is primary:
            continue
        known = _story_urls(primary)
        primary["sources"] = primary.get("sources", []) + [entry for entry in other.get("sources", []) if canonicalize_url(entry.get("url")) not in known]
        stored.remove(other)
    if len(matches) > 1:
        primary["source_count"] = len({entry["name"] for entry in primary["sources"] if entry.get("name")}) or 1
    return primary


def _dedupe_incoming(stories, threshold):
    """Within one run the same story may arrive from both modes; keep one and union its sources."""
    kept = []
    for story in stories:
        twin = find_match(story, kept, threshold)
        if twin is None:
            kept.append(copy.deepcopy(story))
            continue
        known = _story_urls(twin)
        twin["sources"] = twin.get("sources", []) + [entry for entry in story.get("sources", []) if canonicalize_url(entry.get("url")) not in known]
        twin["source_count"] = len({entry["name"] for entry in twin["sources"] if entry.get("name")}) or 1
    return kept


def _apply_incoming(target, story, now_iso, config):
    """Update a stored story from a re-seen one. Returns True when something material changed."""
    known = _story_urls(target)
    new_sources = [entry for entry in story.get("sources", []) if canonicalize_url(entry.get("url")) not in known]
    old_score = float(target.get("relevance_score", 0))
    score_changed = abs(float(story.get("relevance_score", 0)) - old_score) >= config["updated"]["min_score_change"]
    if not new_sources and not score_changed:
        return False   # an unchanged story is left exactly as stored
    reasons = (["score_change"] if score_changed else []) + (["new_source"] if new_sources else [])
    refreshed = copy.deepcopy(story)
    for key in NARRATIVE_FIELDS:
        if key in target:
            refreshed[key] = target[key]     # keep the old narrative until a new one replaces it
    refreshed["narrative_status"] = NARRATIVE_PENDING
    merged_sources = target.get("sources", []) + new_sources
    refreshed.update({
        "story_id": target["story_id"], "id": target["story_id"],
        "first_seen_at": target["first_seen_at"], "last_updated_at": now_iso,
        "previous_score": old_score, "update_reasons": reasons,
        "sources": merged_sources,
        "source_count": len({entry["name"] for entry in merged_sources if entry.get("name")}) or 1,
    })
    target.clear()
    target.update(refreshed)
    return True


def build_day(existing_day, previous_day, briefings, now, config=None):
    """Merge this run's stories into today's archive file.

    Nothing already stored is ever removed; a story seen yesterday keeps its first_seen_at.
    Returns the new day payload, or the existing one when no briefing succeeded.
    """
    config = config or load_badges_config()
    ordered = [briefings[mode] for mode in ("daily", "hourly") if mode in briefings]
    if not ordered:
        return existing_day
    threshold = config["title_match_threshold"]
    now_iso = to_iso(now)
    today = day_key(now, config)

    stored = [copy.deepcopy(story) for story in (existing_day or {}).get("stories", []) if story.get("story_id")]
    previous = [story for story in (previous_day or {}).get("stories", []) if story.get("story_id")]
    for story in _dedupe_incoming([s for briefing in ordered for s in briefing.get("stories", [])], threshold):
        target = _consolidate(stored, story, threshold)
        if target is None:
            carried = find_match(story, previous, threshold)
            if carried is not None:
                target = copy.deepcopy(carried)   # same story as yesterday: keep its history
                stored.append(target)
        if target is None:
            fresh = copy.deepcopy(story)
            fresh.update({"id": fresh["story_id"], "first_seen_at": now_iso, "last_updated_at": now_iso, "update_reasons": []})
            stored.append(fresh)
        else:
            _apply_incoming(target, story, now_iso, config)

    head = {key: value for key, value in ordered[0].items() if key not in HEAD_KEYS_TO_DROP}
    day = {**head, "date": today, "timezone": config["timezone"], "stories": stored}
    present_stories(day, now, config)   # stored order and badges reflect the moment of writing
    return day


# --- badges, ordering, views -------------------------------------------------------------

def compute_badges(story, now, config=None):
    """Badges from stored timestamps only; they disappear on their own when their time is up."""
    config = config or load_badges_config()
    first_seen = parse_iso(story.get("first_seen_at"))
    if first_seen is None:
        return []
    hours = lambda moment: (now - moment).total_seconds() / 3600  # noqa: E731
    published = parse_iso(story.get("published_at_iso"))
    fresh_publication = published is None or hours(published) <= config["max_publication_age_hours"]
    age = hours(first_seen)
    badges = []
    breaking = config["breaking"]
    allowed_type = story.get("event_type") in breaking["allowed_event_types"] and _meets_type_requirement(story, breaking)
    if allowed_type and fresh_publication and 0 <= age <= breaking["max_age_hours"] and float(story.get("relevance_score", 0)) >= breaking["critical_score"]:
        badges.append(BADGE_BREAKING)
    if fresh_publication and 0 <= age <= config["new"]["max_age_hours"]:
        badges.append(BADGE_NEW)
    updated_at = parse_iso(story.get("last_updated_at"))
    if updated_at and updated_at > first_seen and 0 <= hours(updated_at) <= config["updated"]["max_age_hours"]:
        badges.append(BADGE_UPDATED)
    return badges


def _meets_type_requirement(story, breaking):
    """Some types are only breaking from reliable sources (company results yes, stock commentary no)."""
    requirement = breaking.get("type_requirements", {}).get(story.get("event_type"))
    if not requirement:
        return True
    return float((story.get("score_components") or {}).get("source_reliability", 0)) >= requirement["min_source_reliability"]


def _order_key(story):
    first_seen = parse_iso(story.get("first_seen_at"))
    return (
        0 if BADGE_BREAKING in story.get("badges", []) else 1,
        -float(story.get("relevance_score", 0)),
        -(first_seen.timestamp() if first_seen else 0),
        story.get("story_id", ""),
    )


def level_for(score, levels):
    """The score band a story falls into (highest min_score it reaches), or None below every band."""
    for level in sorted(levels, key=lambda item: -item["min_score"]):
        if float(score) >= level["min_score"]:
            return level
    return None


def is_listed(story):
    """Whether the story belongs in the main list (the archive-only low band does not)."""
    return story.get("listed", True)


def present_stories(day, now, config=None, levels=None):
    """Set badges and score band on every story and order them: breaking first, then score, then newest."""
    config = config or load_badges_config()
    levels = load_relevance_config().get("levels") if levels is None else levels
    for story in day.get("stories", []):
        story["badges"] = compute_badges(story, now, config)
        if levels:
            level = level_for(story.get("relevance_score", 0), levels)
            story["level"] = level["name"] if level else "below"
            story["level_label"] = level["label"] if level else ""
            story["listed"] = bool(level and level["listed"])
    day["stories"] = sorted(day.get("stories", []), key=_order_key)
    return day


def hourly_view(day, now, config=None):
    """Only stories first seen or materially updated within the hourly window."""
    config = config or load_badges_config()
    window = timedelta(hours=config["hourly_view_window_hours"])
    def recent(story):
        moments = [parse_iso(story.get("first_seen_at")), parse_iso(story.get("last_updated_at"))]
        return any(moment and timedelta(0) <= now - moment <= window for moment in moments)
    view = {**day, "stories": [story for story in day.get("stories", []) if recent(story)]}
    return view


def fingerprint(day):
    """Hash of everything that matters; ignores run times, badges, ordering and market commentary."""
    if not day:
        return None
    core = {key: value for key, value in day.items() if key not in VOLATILE_DAY_KEYS and key != "stories"}
    core["stories"] = sorted(
        ({key: value for key, value in story.items() if key not in VOLATILE_STORY_KEYS} for story in day.get("stories", [])),
        key=lambda story: story.get("story_id", ""),
    )
    market = day.get("market") or {}
    core["market"] = {key: market.get(key) for key in ("status", "skipped", "errors", "items")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
