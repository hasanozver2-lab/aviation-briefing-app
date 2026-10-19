"""Official airline social posts as ONE logical catalog source ("Official social (airline accounts)").

Posts are collected on the owner's own computer (scripts/collect_social.py, with the owner's own session) and published as
briefings/social_items.json on the data branch. The daily pipeline only READS that file: no session value ever reaches GitHub.
An item is a post's first line (title), a short summary, its time and the post's own link; the stories are headline_only.
"""

import re
from datetime import datetime, timedelta, timezone

try:
    from . import briefing_store, feed_discovery as fd, feed_sources, source_catalog
except ImportError:
    import briefing_store
    import feed_discovery as fd
    import feed_sources
    import source_catalog

SOURCE_NAME = "Official social (airline accounts)"
ITEMS_PATH = f"{briefing_store.BRIEFING_PREFIX}/social_items.json"
STATUS_NO_DATA = "not_configured"
NO_DATA_NOTE = "Yerel sosyal toplayıcı henüz veri yayınlamadı (scripts/collect_social.py --publish)"
STALE_AFTER_HOURS = 36
TITLE_CHARS = 140
URL_PATTERN = re.compile(r"https?://\S+")


def post_title(text):
    """First line of the post without links, shortened at a word boundary."""
    first_line = URL_PATTERN.sub("", (text or "").strip().split("\n")[0]).strip()
    if len(first_line) <= TITLE_CHARS:
        return first_line
    return first_line[:TITLE_CHARS].rsplit(" ", 1)[0].rstrip(",;:- ") + "…"


def post_summary(text):
    return " ".join(URL_PATTERN.sub("", text or "").split())[:feed_sources.FEED_ONLY_SUMMARY_CHARS]


def parse_time(value):
    parsed = fd.parse_datetime(value)
    if parsed:
        return parsed
    try:
        return datetime.strptime(str(value), "%a %b %d %H:%M:%S %z %Y")      # X's own format
    except ValueError:
        return None


WIRE_HANDLES = {"reutersbiz", "business", "ft", "wsj", "cnbc", "markets", "reuters"}
ANALYST_ROLES = {
    "Aviation Analyst & Broadcaster",
    "Editor-in-Chief, The Air Current",
    "Pulitzer Aerospace Reporter",
    "The Airline Observer",
    "Aviation Reporter, Skift & Airline Weekly",
    "Aerospace Analyst",
}
BREAKING_KEYWORDS = re.compile(
    r"\b(breaking|alert|urgent|flaş|flas|son dakika|just in|emergency|ground stop|directive)\b",
    re.IGNORECASE,
)


def article_from_post(post, record):
    published = parse_time(post.get("published_at"))
    title, link = post_title(post.get("text", "")), post.get("link", "")
    if not (published and title and link.startswith("https://")):
        return None
    handle = (post.get("handle") or "").lower()
    text = post.get("text", "")
    if handle in WIRE_HANDLES:
        filter_cfg = feed_sources.load_aviation_filter()
        if not feed_sources.keyword_hit(text, filter_cfg["keywords"]):
            return None
    article = feed_sources.article_from_item(fd.Item(title, link, published, post_summary(text)), record)
    airline = post.get("airline", "")
    author = post.get("author", "")
    role = post.get("role", "")
    platform = post.get("platform", "X")
    if author and not airline:
        source_label = f"{author} on {platform}"
    elif airline:
        source_label = f"{airline} on {platform}"
    else:
        source_label = SOURCE_NAME

    is_wire = handle in WIRE_HANDLES
    is_analyst = (
        role in ANALYST_ROLES
        or any(a in (author or "").lower() for a in ("jon ostrower", "ned russell", "dominic gates", "brian sumers", "alex macheras"))
        or any(h in handle for h in ("jonostrower", "nedrussell", "dominicgates", "briansumers", "alexinair", "leehamnews"))
    )
    has_breaking = bool(BREAKING_KEYWORDS.search(text))

    # Social feeds should not falsely masquerade as official SEC/KAP filings (tier 1 official)
    # Only official verified corporate accounts of airlines/OEMs/regulators receive official=True
    is_official_channel = bool(airline and not is_wire and not is_analyst)
    tier = 1 if is_official_channel else 2
    is_flash = is_wire or is_analyst or has_breaking

    article.update(
        source=source_label,
        airline=airline,
        airline_code=post.get("airline_code", ""),
        via_social=True,
        is_flash_alert=is_flash,
        official=is_official_channel,
        source_type="official_social" if is_official_channel else "social",
        tier=tier,
    )
    return article


def catalog_record(rows=None):
    row = next((row for row in (rows or source_catalog.read_rows()) if row["name"] == SOURCE_NAME), None)
    return feed_sources.source_record(row) if row else None


def collect(now, cutoff, read_json=None, rows=None):
    """(articles, report) for the whole logical source; report never carries post text."""
    payload = (read_json or briefing_store.read_json)(ITEMS_PATH)
    if not payload or not payload.get("posts"):
        return [], {"status": STATUS_NO_DATA, "error": NO_DATA_NOTE, "articles": 0}
    record = catalog_record(rows)
    if record is None:
        return [], {"status": "error", "error": f"{SOURCE_NAME} is missing from the catalog", "articles": 0}
    generated = parse_time(payload.get("generated_at"))
    note = ""
    if not generated or now - generated > timedelta(hours=STALE_AFTER_HOURS):
        note = "yerel toplama 36 saatten eski; toplayıcıyı yeniden çalıştırın"
    articles = [article for article in (article_from_post(post, record) for post in payload["posts"])
                if article and article["timestamp"] >= cutoff.timestamp()]
    articles.sort(key=lambda article: article["timestamp"], reverse=True)
    return articles, {"status": "active", "error": note, "articles": len(articles), "posts_read": len(payload["posts"])}
