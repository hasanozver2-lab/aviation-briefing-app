"""Google Alerts feeds as ONE logical catalog source ("Google Alerts (wire headlines)").

The feed addresses are secret: they come from the ALERT_FEEDS variable (one per line) and are never logged, written to
status.json or a report, or put in an error message. Everything that leaves this module names a feed "alert feed N".
Only the feed addresses are requested. The article pages of the publishers are NEVER fetched: an item contributes its title,
a short summary, its time and the publisher's own link, taken from the feed entry.
"""

import urllib.parse
import xml.etree.ElementTree as ET

try:
    from . import feed_discovery as fd
    from . import feed_sources, language, source_catalog
except ImportError:
    import feed_discovery as fd
    import feed_sources
    import language
    import source_catalog

ENV_NAME = "ALERT_FEEDS"
SOURCE_NAME = "Google Alerts (wire headlines)"
STATUS_NOT_CONFIGURED = "not_configured"
NOT_CONFIGURED_NOTE = "ALERT_FEEDS tanımlı değil; Google Alerts beslemeleri okunmadı"
GOOGLE_REDIRECT_PARAMS = ("url", "q")
GOOGLE_HOST_PREFIX = "google."
PUBLISHER_NAMES = {
    "reuters.com": "Reuters", "bloomberg.com": "Bloomberg", "wsj.com": "WSJ", "apnews.com": "AP", "ft.com": "FT",
    "nytimes.com": "The New York Times", "washingtonpost.com": "The Washington Post", "cnbc.com": "CNBC", "economist.com": "The Economist",
    "bbc.com": "BBC", "bbc.co.uk": "BBC", "aviationweek.com": "Aviation Week", "flightglobal.com": "FlightGlobal", "simpleflying.com": "Simple Flying",
    "cnn.com": "CNN", "theguardian.com": "The Guardian", "forbes.com": "Forbes", "marketwatch.com": "MarketWatch", "airlinerating.com": "AirlineRatings",
}


def parse_feed_urls(raw):
    """(urls, ignored_count): one http(s) address per line; blank lines and comments are skipped, anything else is counted but never echoed."""
    urls, ignored = [], 0
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parsed = urllib.parse.urlparse(line)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            urls.append(line)
        else:
            ignored += 1
    return list(dict.fromkeys(urls)), ignored


def target_url(link):
    """The publisher's address inside a Google redirect (`url` parameter); a non-Google link is returned as it is. '' when unusable."""
    parsed = urllib.parse.urlparse(link or "")
    host = (parsed.hostname or "").lower()
    if not host:
        return ""
    if host.removeprefix("www.").startswith(GOOGLE_HOST_PREFIX):
        query = urllib.parse.parse_qs(parsed.query)
        link = next((query[name][0] for name in GOOGLE_REDIRECT_PARAMS if query.get(name)), "")
    target = urllib.parse.urlparse(link)
    return link if target.scheme in ("http", "https") and target.netloc else ""


def publisher_name(url):
    """reuters.com -> Reuters; an unknown domain becomes its capitalised main label (example-news.com -> Example News)."""
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    for domain, name in PUBLISHER_NAMES.items():
        if host == domain or host.endswith("." + domain):
            return name
    main_label = source_catalog.registrable_key(url).split(".")[0]
    return " ".join(part.capitalize() for part in main_label.replace("_", "-").split("-")) or host


def failure_note(position, status=0, error=""):
    """What may be said about a failed feed: its position and a status code or exception class, never the address."""
    what = f"HTTP {status}" if status else (error.split(":")[0].split(" ")[0] or "no response")
    return f"alert feed {position}: {what}"


def read_feed(fetcher, url, position):
    """(items, note) for one feed address. note is '' on success."""
    try:
        response = fetcher.get(url, conditional=True)
    except Exception as exc:          # the exception text may contain the address
        return [], failure_note(position, error=type(exc).__name__)
    if response.status == 304:
        return [], ""
    if response.status != 200:
        return [], failure_note(position, response.status, response.error or "")
    try:
        _, items = fd.parse_feed(response.body)
    except (ET.ParseError, ValueError):
        return [], f"alert feed {position}: not a valid feed"
    return items, ""


def article_from_alert(item, record):
    link = target_url(item.link)
    if not link:
        return None
    article = feed_sources.article_from_item(item, record)
    article.update(link=link, source=publisher_name(link), via_alert=True)
    article["language"] = language.detect_language(f"{article['title']} {article['description']}")
    return article


def catalog_record(rows=None):
    row = next((row for row in (rows or source_catalog.read_rows()) if row["name"] == SOURCE_NAME), None)
    return feed_sources.source_record(row) if row else None


def collect(raw_urls, now, cutoff, entity_index_factory=None, fetcher=None, rows=None):
    """(articles, report) for the whole logical source. Each configured feed is read once; report has no address in it."""
    urls, ignored = parse_feed_urls(raw_urls)
    if not urls:
        return [], {"status": STATUS_NOT_CONFIGURED, "error": NOT_CONFIGURED_NOTE, "articles": 0}
    record = catalog_record(rows)
    if record is None:
        return [], {"status": "error", "error": f"{SOURCE_NAME} is missing from the catalog", "articles": 0}
    fetcher = fetcher or fd.PoliteFetcher(timeout=record["timeout_s"])
    articles, notes = [], []
    for position, url in enumerate(urls, start=1):
        items, note = read_feed(fetcher, url, position)
        if note:
            notes.append(note)
        recent = [item for item in items if item.title and item.link and item.published and item.published >= cutoff]
        recent.sort(key=lambda item: item.published, reverse=True)
        articles.extend(filter(None, (article_from_alert(item, record) for item in recent[:feed_sources.MAX_ITEMS_PER_SOURCE])))
    read = len(articles)
    dropped = 0
    if articles and entity_index_factory:
        articles, dropped = feed_sources.filter_for_aviation(articles, entity_index_factory())
    if ignored:
        notes.append(f"{ignored} ALERT_FEEDS line(s) ignored: not an http(s) address")
    return articles, {"status": "active", "error": "; ".join(notes), "articles": len(articles), "feeds": len(urls), "items_read": read, "filtered_out": dropped}


def publisher_counts(articles):
    counts = {}
    for article in articles:
        counts[article["source"]] = counts.get(article["source"], 0) + 1
    return dict(sorted(counts.items(), key=lambda pair: -pair[1]))
