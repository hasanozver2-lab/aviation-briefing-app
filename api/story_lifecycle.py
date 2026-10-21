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
from urllib.parse import urlparse

try:
    from . import clustering, language, source_catalog, source_registry, text_match
    from .urls import canonicalize_url
except ImportError:
    import clustering
    import language
    import source_registry
    import source_catalog
    import text_match
    from urls import canonicalize_url


BASE_DIR = Path(__file__).resolve().parent.parent
BADGES_CONFIG_PATH = BASE_DIR / "config" / "badges.json"
RELEVANCE_CONFIG_PATH = BASE_DIR / "config" / "relevance.json"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BADGE_NEW, BADGE_UPDATED, BADGE_BREAKING = "new", "updated", "breaking"
# Not part of the change fingerprint: they differ on every run without meaning anything.
VOLATILE_DAY_KEYS = {"generated_at", "time_str", "last_pipeline_run_at", "last_pipeline_attempt_at", "heading", "warning", "market", "airspace_radar", "earnings_calendar", "fleet_watch", "badges"}
VOLATILE_STORY_KEYS = {"badges"}
HEAD_KEYS_TO_DROP = {"stories"}
# The LLM-written part of a story. It is kept when a story is refreshed, and regenerated only after
# a material update (narrative_status goes back to "pending" until then).
NARRATIVE_FIELDS = (
    "headline", "lead", "detailed_analysis", "data_points", "strategic_impact", "market_exposure",
    "why_it_matters", "thy_impact_assessment", "related_news", "narrative_generated_at", "narrative_language",
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


def is_strategic_report(item):
    """Whether an article or story is a strategic outlook, forecast, index, or benchmark report."""
    if not isinstance(item, dict):
        return False
    if item.get("strategic_publication"):
        return True
    orig = item.get("original_source") if isinstance(item.get("original_source"), dict) else {}
    url = str(item.get("link") or orig.get("url") or "").lower()
    if any(pattern in url for pattern in STRATEGIC_REPORT_URL_PATTERNS):
        return True
    title = " ".join(
        str(part)
        for part in (item.get("title"), item.get("headline"), orig.get("title"))
        if part
    )
    if "interview" in title.lower():
        return False
    if item.get("is_strategic_report"):
        return True
    if STRATEGIC_REPORT_TITLE_PATTERN.search(title):
        return True
    publisher = str(item.get("source") or orig.get("source_name") or "").strip().lower()
    if publisher in BENCHMARK_INSTITUTION_SOURCES and BENCHMARK_REPORT_KEYWORDS.search(f"{title} {url}"):
        return True
    return False


def is_flash_alert(item):
    """Whether an article or story is a fast flash alert from analyst radar or breaking wire/social."""
    if not isinstance(item, dict):
        return False
    if item.get("is_flash_alert"):
        return True
    orig = item.get("original_source") if isinstance(item.get("original_source"), dict) else {}
    url = str(item.get("link") or orig.get("url") or "").lower()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in ("theaircurrent.com", "airlineweekly.com") or any(
        host.endswith("." + d) for d in ("theaircurrent.com", "airlineweekly.com")
    ):
        return True
    source_name = str(item.get("source") or orig.get("source_name") or "").lower()
    if any(a in source_name for a in ("the air current", "jon ostrower", "ned russell", "airline weekly", "dominic gates", "brian sumers")):
        return True
    title = str(item.get("title") or item.get("headline") or "").lower()
    if any(k in title for k in ("flash alert", "breaking signal", "kısa sinyal", "the air current:", "jon ostrower:")):
        return True
    return False


STRATEGIC_REPORT_URL_PATTERNS = (
    "/commercial/market/commercial-market-outlook",
    "/global-market-forecast",
    "eurocontrol.int/publication/",
    "eurocontrol.int/forecasting",
    "oag.com/megahubs",
    "ideaworkscompany.com/reports",
    "ideaworkscompany.com/wp-content/uploads",
    "iata.org/en/publications/",
    "aci.aero/news-and-resources/publications/",
    "airbus.com/en/products-services/commercial-aircraft/market/",
    "faa.gov/data_research/aviation/aerospace_forecasts",
    "oliverwyman.com/our-expertise/insights",
    "atag.org/our-publications",
)

STRATEGIC_REPORT_TITLE_PATTERN = re.compile(
    r"\b(?:"
    r"commercial\s+market\s+outlook|global\s+market\s+forecast|"
    r"eurocontrol\s+forecast|seven-year\s+forecast|seven‑year\s+forecast|"
    r"european\s+aviation\s+overview|megahubs|"
    r"yearbook\s+of\s+ancillary\s+revenue|ancillary\s+revenue\s+yearbook|"
    r"pilot\s+and\s+technician\s+outlook|services\s+market\s+outlook|"
    r"global\s+outlook\s+for\s+air\s+transport|world\s+airport\s+traffic|"
    r"fleet\s+forecast|global\s+services\s+forecast|"
    r"air\s+passenger\s+market\s+analysis|air\s+cargo\s+market\s+analysis|"
    r"world\s+air\s+transport\s+statistics|airport\s+traffic\s+report|busiest\s+airports|"
    r"wats\s+report|passenger\s+traffic\s+forecast|"
    r"faa\s+aerospace\s+forecast|fleet\s+and\s+mro\s+forecast|"
    r"aviation\s+benefits\s+beyond\s+borders|annual\s+safety\s+review"
    r")\b",
    flags=re.IGNORECASE,
)

BENCHMARK_INSTITUTION_SOURCES = {
    "ideaworkscompany",
    "oag",
    "cirium",
    "eurocontrol",
    "iata",
    "aci world",
    "aci",
    "icao",
    "faa",
    "easa",
    "boeing",
    "airbus",
    "embraer",
    "oliver wyman",
    "atag",
    "capa centre for aviation",
    "capa",
}

BENCHMARK_REPORT_KEYWORDS = re.compile(
    r"\b(?:"
    r"forecast|forecasts|outlook|yearbook|megahubs|report|index|overview|study|"
    r"benchmark|whitepaper|bulletin|ancillary\s+revenue|on-time\s+performance|"
    r"capacity\s+trends|connect(?:ing|ivity)|brand-loyal|a\s+la\s+carte|"
    r"passenger\s+demand|cargo\s+demand|traffic\s+data|passenger\s+traffic|"
    r"deliveries\s+(?:through|by)\s+20[34]\d"
    r")\b",
    flags=re.IGNORECASE,
)


def published_on_day(story, date_text, config, now=None):
    """Whether a story belongs to a local archive day by publication time.

    A source date is authoritative. First-seen time is only a fallback for the
    rare legacy record without one; this keeps a delayed feed item from appearing
    as new merely because the pipeline first encountered it today.
    """
    if is_strategic_report(story):
        return True
    published = parse_iso(story.get("published_at_iso"))
    first_seen = parse_iso(story.get("first_seen_at"))
    moment = published or first_seen
    if not moment:
        return False
    local_day = day_key(moment, config)
    if local_day == date_text:
        return True
    allowed_prev_day = previous_day_key(date_text)
    if local_day == allowed_prev_day:
        if published and first_seen and day_key(first_seen, config) == date_text:
            delay_h = (first_seen - published).total_seconds() / 3600
            if delay_h >= 12:
                return False
        max_age = (config or {}).get("rolling_retention_hours", 0)
        if max_age > 0:
            current_moment = now if now is not None else utc_now()
            age_hours = (current_moment - moment).total_seconds() / 3600
            return 0 <= age_hours <= max_age
    return False


def drop_not_published_on_day(day, date_text, config, now=None):
    """Apply the current-day view without changing an archive file on disk."""
    stories = day.get("stories", [])
    day["stories"] = [story for story in stories if published_on_day(story, date_text, config, now=now)]
    return len(stories) - len(day["stories"])


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
    if (is_strategic_report(article) or is_flash_alert(article)) and article.get("tier"):
        tier = min(tier, article["tier"]) if tier else article["tier"]
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
    return {
        "name": str(article.get("source", "")), "url": str(article.get("link", "")), "title": str(article.get("title", "")),
        "language": article.get("language") or language.detect_language(f"{article.get('title', '')} {article.get('description', '')}"),
    }


def _fuse_cluster_descriptions(representative, members):
    """Combine distinct descriptions across clustered articles so a representative inherits corroborated facts."""
    base = str(representative.get("description") or "").strip()
    parts = [base] if base else []
    seen_lower = {base.lower()} if base else set()
    for member in members:
        if member is representative:
            continue
        desc = str(member.get("description") or "").strip()
        title = str(member.get("title") or "").strip()
        src = str(member.get("source") or "").strip()
        snippet = f"{title}. {desc}".strip(". ") if desc else title
        if not snippet or snippet.lower() in seen_lower:
            continue
        if any(snippet.lower() in existing for existing in seen_lower):
            continue
        seen_lower.add(snippet.lower())
        parts.append(f"[{src}] {snippet}" if src else snippet)
    return " | ".join(parts)


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
            sources = [{"name": str(source.get("source_name", "")), "url": str(source.get("url", "")), "title": str(source.get("title", "")),
                        "language": language.article_language(source.get("source_name"), source.get("title", ""))}]
        else:
            article = articles[index]
            members = [articles[i] for i in cluster_by_index.get(index, [index])]
            sources, seen = [], set()
            for member in sorted(members, key=lambda item: (item.get("timestamp", 0), item.get("link", ""))):
                canonical = canonicalize_url(member.get("link"))
                if canonical and canonical not in seen:
                    seen.add(canonical)
                    sources.append(_source_entry(member))
            if len(members) > 1 or article.get("description"):
                fused = _fuse_cluster_descriptions(article, members)
                max_len = 300 if story.get("basis") == "headline_only" else 1200
                if len(fused) > len(str(story.get("source_description") or "")):
                    story["source_description"] = fused[:max_len]
        publishers = {entry["name"] for entry in sources if entry["name"]}
        score, components = score_article(article, max(1, len(publishers)), config)
        published = article.get("timestamp")
        img = str(story.get("image_url") or article.get("image_url") or "")
        body = str(story.get("article_body") or article.get("article_body") or story.get("source_description") or "")
        if not img:
            for member in members:
                if member.get("image_url"):
                    img = str(member["image_url"])
                    break
        if not body:
            for member in members:
                if member.get("article_body"):
                    body = str(member["article_body"])
                    break
        story.update({
            "story_id": story.get("id") or stable_story_id(source.get("url"), story.get("headline")),
            "relevance_score": score,
            "score_components": components,
            "sources": sources,
            "source_count": max(1, len(publishers)),
            "published_at_iso": to_iso(datetime.fromtimestamp(published, tz=timezone.utc)) if isinstance(published, (int, float)) and published > 0 else "",
            "is_strategic_report": bool(is_strategic_report(story) or is_strategic_report(article)),
            "is_flash_alert": bool(is_flash_alert(story) or is_flash_alert(article)),
            "publication_date_status": article.get("publication_date_status", "verified" if published else "unknown"),
            "image_url": img,
            "article_body": body,
        })
        story["language"] = language.story_language(story)
    return stories


def cluster_representatives(articles):
    """One article per group of near-identical titles: the most reliable source, earliest among equals."""
    representatives = []
    for indexes in clustering.cluster_articles(articles):
        members = [articles[index] for index in indexes]
        representatives.append(max(members, key=lambda a: (a.get("reliability_weight") or 0, bool(a.get("official")), -a.get("timestamp", 0))))
    return representatives


def military_strike_matches(text, selection):
    """A strike with a military context and no labour context (selection.military_strike)."""
    rule = selection.get("military_strike")
    if not rule:
        return False
    prepared = text_match.prepare(text)
    return (text_match.TermSet(rule["requires"]).any(prepared) and text_match.TermSet(rule["context"]).any(prepared)
            and not text_match.TermSet(rule["unless"]).any(prepared))


def is_military_story(story, selection):
    """Defence/military items that do not involve any airline or civil aviation context are out of scope."""
    exclude_terms = selection.get("exclude_terms")
    if not exclude_terms:
        return False
    title = story.get("headline", "")
    is_defence_item = text_match.TermSet(exclude_terms).any(title) or military_strike_matches(title, selection)
    if not is_defence_item or text_match.TermSet(selection.get("keep_terms", [])).any(title):
        return False
    entities = story.get("entities") or {}
    return not (entities.get("carriers") or entities.get("groups"))


def _story_filter_text(story):
    """Source-written text used by deterministic read-time exclusions."""
    parts = [story.get("headline", ""), story.get("source_description", "")]
    parts.append((story.get("original_source") or {}).get("title", ""))
    parts.extend(source.get("title", "") for source in story.get("sources", []) if isinstance(source, dict))
    return " ".join(str(part) for part in parts if part)


def is_ground_traffic_story(story, selection):
    """Road incidents merely located near an airport are outside the aviation brief."""
    rule = selection.get("ground_traffic") or {}
    if not rule:
        return False

    text = _story_filter_text(story)
    has_road_term = text_match.TermSet(rule.get("road_terms", [])).any(text)
    has_road_route = any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in rule.get("road_route_patterns", []))
    has_incident = text_match.TermSet(rule.get("incident_terms", [])).any(text)
    if not (has_incident and (has_road_term or has_road_route)):
        return False

    entities = story.get("entities") or {}
    has_aircraft = bool(entities.get("aircraft") or entities.get("aircraft_types"))
    has_direct_aviation_context = text_match.TermSet(rule.get("aviation_keep_terms", [])).any(text)
    return not (has_aircraft or has_direct_aviation_context)


def is_excluded(story, relevance):
    """Current deterministic exclusions from config/relevance.json."""
    selection = relevance["selection"]
    return not has_direct_link(story, selection) or has_only_unverified_sources(story, selection) or is_military_story(story, selection) or is_ground_traffic_story(story, selection) or bool(
        selection.get("exclude_commentary") and is_finance_commentary(story, relevance.get("commentary"))
    )


RECOGNIZED_REDIRECT_PUBLISHERS = {
    "reuters", "bloomberg", "aviation week", "ch-aviation", "wsj", "the wall street journal",
    "wall street journal", "nyt", "the new york times", "new york times", "ft", "financial times",
    "ap", "ap news", "associated press", "cnbc", "the economist", "economist", "nikkei",
    "nikkei asia", "the air current", "capa", "capa centre for aviation", "cirium", "oag",
    "ideaworkscompany", "ideaworks", "eurocontrol", "flightglobal", "simple flying",
    "aerotime", "airdata news", "airways magazine", "aviation business middle east",
    "runway girl network", "future travel experience", "aviation24", "asian aviation",
    "aviation news.eu", "aero-news network", "ain online", "leeham news", "air cargo news",
    "skift", "the points guy", "daily sabah", "anadolu agency", "anadolu ajansı",
    "hürriyet daily news", "trt world", "the aviation hub", "turkish airlines", "airbus",
    "boeing", "embraer", "rtx", "pratt & whitney", "safran", "rolls-royce", "pr newswire",
    "globenewswire", "business wire", "phocuswire", "bbc", "cnn", "forbes", "the guardian",
    "marketwatch", "washington post", "the washington post"
}


def is_legacy_unverified_test_story(story):
    """Check if story is an unverified dummy/legacy test fixture with synthetic URL."""
    urls = [url for url in [(story.get("original_source") or {}).get("url")] + [s.get("url") for s in story.get("sources", [])] if url]
    for url in urls:
        clean = url.split("?")[0].rstrip("/")
        if any(clean.endswith(suffix) for suffix in ("/old", "/search", "/fake")):
            return True
    return False


def is_recognized_publisher_story(story):
    """Check if any source in the story is an approved wire, trade media or recognized publisher."""
    if is_legacy_unverified_test_story(story):
        return False
    names = []
    original = story.get("original_source") or {}
    if original.get("source_name"):
        names.append(str(original["source_name"]).strip().lower())
    for s in story.get("sources", []):
        if s.get("name"):
            names.append(str(s["name"]).strip().lower())
    for name in names:
        if name in RECOGNIZED_REDIRECT_PUBLISHERS:
            return True
        if any(pub in name for pub in ("reuters", "bloomberg", "aviation week", "ch-aviation", "wall street journal", "new york times", "financial times", "associated press", "cnbc", "cirium", "capa", "the air current")):
            return True
    return False


def _is_direct_link(url, blocked):
    """A real article address: http(s), a host, and not a search/redirect host."""
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").lower()
    if not (parsed.scheme in ("http", "https") and "." in host):
        return False
    if host in blocked:
        return False
    return True


def has_direct_link(story, selection):
    blocked = set(selection.get("unverified_source_hosts", []))
    urls = [url for url in [(story.get("original_source") or {}).get("url")] + [entry.get("url") for entry in story.get("sources", [])] if url]
    if any(_is_direct_link(url, blocked) for url in urls):
        return True
    if is_recognized_publisher_story(story):
        for url in urls:
            parsed = urlparse(str(url).strip())
            host = (parsed.hostname or "").lower()
            if parsed.scheme in ("http", "https") and "." in host and (host in blocked or host.endswith(".google.com")):
                return True
    return False


def ensure_direct_link(story, selection):
    """Every served story links to a real article. A redirect link as the main source is replaced by the first direct source;
    redirect-only entries are removed from the source list unless from a recognized publisher. Returns False when no usable link exists."""
    blocked = set(selection.get("unverified_source_hosts", []))

    # Resolve recognized publisher Google News links to real direct publisher links
    if is_recognized_publisher_story(story):
        try:
            from . import urls
        except ImportError:
            import urls
        for entry in story.get("sources", []):
            u = entry.get("url", "")
            if (urlparse(u).hostname or "").lower() in blocked:
                resolved = urls.unshorten_google_news_url(u)
                if resolved and _is_direct_link(resolved, blocked):
                    entry["url"] = resolved
        orig = story.get("original_source") or {}
        orig_url = orig.get("url", "")
        if (urlparse(orig_url).hostname or "").lower() in blocked:
            resolved = urls.unshorten_google_news_url(orig_url)
            if resolved and _is_direct_link(resolved, blocked):
                orig["url"] = resolved
                story["original_source"] = orig

    pure_direct = [entry for entry in story.get("sources", []) if _is_direct_link(entry.get("url"), blocked)]
    original = dict(story.get("original_source") or {})
    original_is_pure_direct = _is_direct_link(original.get("url"), blocked)

    if original_is_pure_direct:
        if len(pure_direct) != len(story.get("sources", [])):
            story["sources"] = pure_direct
            story["source_count"] = min(story.get("source_count", len(pure_direct)), len(pure_direct)) or len(pure_direct)
        return True

    if pure_direct:
        first = pure_direct[0]
        original.update(url=first["url"], title=first.get("title") or original.get("title", ""), source_name=first.get("name") or original.get("source_name", ""))
        story["original_source"] = original
        story["sources"] = pure_direct
        story["source_count"] = min(story.get("source_count", len(pure_direct)), len(pure_direct)) or len(pure_direct)
        return True

    if is_recognized_publisher_story(story):
        redirect_sources = [entry for entry in story.get("sources", []) if urlparse(entry.get("url", "")).scheme in ("http", "https")]
        if not redirect_sources and urlparse(original.get("url", "")).scheme in ("http", "https"):
            redirect_sources = [original]
        if redirect_sources:
            if not _is_direct_link(original.get("url"), blocked):
                first = redirect_sources[0]
                original.update(url=first["url"], title=first.get("title") or original.get("title", ""), source_name=first.get("name") or original.get("source_name", ""))
                story["original_source"] = original
            story["sources"] = redirect_sources
            story["source_count"] = min(story.get("source_count", len(redirect_sources)), len(redirect_sources)) or len(redirect_sources)
            return True

    return False


def has_only_unverified_sources(story, selection):
    """Legacy search redirects without a recognized publisher are not publisher evidence; leave their archived records intact."""
    if is_recognized_publisher_story(story):
        return False
    blocked = set(selection.get("unverified_source_hosts", []))
    urls = _story_urls(story)
    if not any((urlparse(url).hostname or "").lower() in blocked for url in urls):
        return False
    approved_domains = {
        source_catalog.registrable_key(row["url"]) for row in source_catalog.read_rows()
        if row.get("active") == "1" and row.get("status") == "active"
        and row.get("license_status") == "public" and not source_catalog.notes_of(row).get("license_required")
    }
    return not any((urlparse(url).hostname or "").lower() not in blocked
                   and source_catalog.registrable_key(url) in approved_domains for url in urls)


def drop_excluded(day, relevance=None):
    """Read-time filter: remove stories the current exclusion lists reject. Returns how many were dropped.

    The archive file is never rewritten here; a story that was archived under older (or no) exclusion rules
    simply stops being served, and comes back if the lists are loosened.
    """
    relevance = relevance or load_relevance_config()
    selection = relevance["selection"]
    kept = [story for story in day.get("stories", []) if not is_excluded(story, relevance) and ensure_direct_link(story, selection)]
    dropped = len(day.get("stories", [])) - len(kept)
    day["stories"] = kept
    return dropped


def select_stories(stories, selection, commentary=None):
    """Stories to archive: the listed ones (score >= min_score, at most max_per_run) and the archive-only low band
    (archive_min_score <= score < min_score, at most max_low_per_run). Strategic reports have their own bucket so they
    never crowd out daily breaking news. Military items and finance commentary are dropped."""
    archive_minimum = selection.get("archive_min_score", selection["min_score"])
    # A story whose safety type was dropped for lack of an airline context (general aviation, contextless crashes) stays in the
    # archive-only band however low it scores: it is hidden from the list, not lost.
    eligible = [
        story for story in stories
        if (float(story.get("relevance_score", 0)) >= archive_minimum or story.get("context_demoted_from")) and not is_military_story(story, selection)
        and not has_only_unverified_sources(story, selection)
        and not is_ground_traffic_story(story, selection)
        and not (selection.get("exclude_commentary") and is_finance_commentary(story, commentary))
    ]
    eligible.sort(key=lambda story: (-float(story["relevance_score"]), story["story_id"]))
    regular_listed = [
        story for story in eligible
        if float(story["relevance_score"]) >= selection["min_score"] and not is_strategic_report(story)
    ][: selection["max_per_run"]]
    strategic_listed = [
        story for story in eligible
        if float(story["relevance_score"]) >= selection["min_score"] and is_strategic_report(story)
    ][: selection.get("max_strategic_per_run", 3)]
    listed = sorted(
        regular_listed + strategic_listed,
        key=lambda story: (-float(story["relevance_score"]), story["story_id"]),
    )
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
        if not primary.get("image_url"):
            for other in matches:
                if other.get("image_url"):
                    primary["image_url"] = other["image_url"]
                    break
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
    # A corrected publisher date must propagate even when score and sources have not changed.
    # It does not create an editorial update or reset the story's discovery history.
    date_status = story.get("publication_date_status")
    has_verified_date = date_status == "verified" and story.get("published_at_iso")
    has_unknown_report_date = date_status == "unknown" and is_strategic_report(story)
    if has_verified_date or has_unknown_report_date:
        for key in ("published_at_iso", "published_at", "publication_date_status"):
            if key in story:
                target[key] = story[key]
    if not target.get("image_url") and story.get("image_url"):
        target["image_url"] = story["image_url"]
    if not target.get("article_body") and story.get("article_body"):
        target["article_body"] = story["article_body"]
    new_sources = [entry for entry in story.get("sources", []) if canonicalize_url(entry.get("url")) not in known]
    old_score = float(target.get("relevance_score", 0))
    score_changed = abs(float(story.get("relevance_score", 0)) - old_score) >= config["updated"]["min_score_change"]
    incoming_desc = str(story.get("source_description") or "")
    if target.get("narrative_status") == NARRATIVE_PENDING and incoming_desc and not target.get("source_description"):
        target["source_description"] = incoming_desc
    if (
        not new_sources
        and not score_changed
        and target.get("narrative_status") == "done"
        and not target.get("data_points")
        and len(incoming_desc) >= 60
        and len(str(target.get("source_description") or "")) < 60
    ):
        target["source_description"] = incoming_desc
        target["narrative_status"] = NARRATIVE_PENDING
        return True
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


MORNING_RESET_HOUR_LOCAL = 8
SCAN_INTERVAL_HOURS = 3


def is_morning_deep_window(now, config=None):
    """Whether `now` falls in the 08:00 Europe/Istanbul morning deep-scan slot (08:00–10:59 local)."""
    config = config or load_badges_config()
    local_now = now.astimezone(local_timezone(config))
    reset_hour = int(config.get("morning_deep_reset_hour_local", MORNING_RESET_HOUR_LOCAL))
    return reset_hour <= local_now.hour < reset_hour + SCAN_INTERVAL_HOURS


def should_run_morning_reset(now, existing_day, config=None):
    """True during the 08:00 local window when today's archive has not yet had its 08:00 full refresh."""
    if not is_morning_deep_window(now, config):
        return False
    if not existing_day:
        return True
    return not bool(existing_day.get("morning_reset_at"))


def build_day(existing_day, previous_day, briefings, now, config=None, morning_reset=False):
    """Merge this run's stories into today's archive file.

    A morning deep scan broadens collection without discarding stored stories or their history.
    Re-seen stories keep their first_seen_at and narratives; all runs merge incrementally.
    """
    config = config or load_badges_config()
    ordered = [briefings[mode] for mode in ("daily", "hourly") if mode in briefings]
    if not ordered:
        return existing_day
    threshold = config["title_match_threshold"]
    now_iso = to_iso(now)
    today = day_key(now, config)

    force_reset = bool(morning_reset or any(isinstance(b, dict) and b.get("force_morning_reset") for b in ordered))
    do_morning_reset = bool(
        force_reset
        or (
            any(isinstance(b, dict) and b.get("morning_deep_scan") for b in ordered)
            and not (existing_day or {}).get("morning_reset_at")
        )
    )
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

    relevance_cfg = load_relevance_config()
    max_strategic = int((relevance_cfg.get("selection") or {}).get("max_strategic_per_run", 3))
    strategic_count = sum(1 for s in stored if is_strategic_report(s))
    for prev_story in previous:
        if is_strategic_report(prev_story) and find_match(prev_story, stored, threshold) is None:
            if strategic_count < max_strategic:
                stored.append(copy.deepcopy(prev_story))
                strategic_count += 1

    head = {
        key: value
        for key, value in ordered[0].items()
        if key not in HEAD_KEYS_TO_DROP and key not in {"morning_deep_scan", "force_morning_reset"}
    }
    day = {**head, "date": today, "timezone": config["timezone"], "stories": stored}
    if do_morning_reset:
        day["morning_reset_at"] = now_iso
    elif existing_day and existing_day.get("morning_reset_at"):
        day["morning_reset_at"] = existing_day["morning_reset_at"]
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
    date_unknown = story.get("publication_date_status") == "unknown"
    fresh_publication = not date_unknown and (published is None or 0 <= hours(published) <= config["max_publication_age_hours"])
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
        story["language"] = language.story_language(story)       # recomputed on every read: sources can be added after the story was stored
        story["is_strategic_report"] = is_strategic_report(story)
        story["is_flash_alert"] = is_flash_alert(story)
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
    radar = day.get("airspace_radar") or {}
    core["airspace_radar"] = {
        "status": radar.get("status"),
        "total_active_zones": radar.get("total_active_zones"),
        "do_not_operate_count": radar.get("do_not_operate_count"),
        "restricted_count": radar.get("restricted_count"),
        "caution_count": radar.get("caution_count"),
        "zones": [
            {
                "country": z.get("country"),
                "fir": z.get("fir"),
                "risk_level": z.get("risk_level"),
                "bulletin_code": z.get("bulletin_code"),
            }
            for z in radar.get("zones", [])
        ],
    }
    cal = day.get("earnings_calendar") or {}
    core["earnings_calendar"] = {
        "status": cal.get("status"),
        "total_events": cal.get("total_events"),
        "events": [
            {"id": e.get("id"), "date": e.get("date"), "status": e.get("status")}
            for e in cal.get("events", [])
        ],
    }
    fleet = day.get("fleet_watch") or {}
    core["fleet_watch"] = {
        "status": fleet.get("status"),
        "total_programs": fleet.get("total_programs"),
        "programs": [
            {"id": p.get("id"), "severity": p.get("severity")}
            for p in fleet.get("programs", [])
        ],
    }
    return hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
