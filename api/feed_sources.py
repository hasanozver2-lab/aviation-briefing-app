"""Catalog sources read through their discovered public feed (config/feeds_discovered.json).

The daily pipeline reads this file and uses the stored address. When an address stops working it re-discovers in
memory for that run and logs it; the file itself is updated only from the verified output of the probe workflow
(scripts/apply_probe.py), never by the pipeline.

Everything taken from a feed is headline, link, publication time and the short feed summary. feed_only sources never
leave that boundary: the summary is used once to write the model's own summary and is not kept or published.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from . import feed_discovery as fd
    from . import language, source_catalog, source_registry
except ImportError:
    import feed_discovery as fd
    import language
    import source_catalog
    import source_registry

BASE_DIR = Path(__file__).resolve().parent.parent
DISCOVERED_PATH = BASE_DIR / "config" / "feeds_discovered.json"
AVIATION_FILTER_PATH = BASE_DIR / "config" / "aviation_filter.json"
MODE_FEED_ONLY = "feed_only"
BASIS_HEADLINE_ONLY = "headline_only"
MAX_ITEMS_PER_SOURCE = 25
FEED_ONLY_SUMMARY_CHARS = 300      # a feed summary is short by nature; this keeps it that way
ENTITY_KINDS_FOR_FILTER = ("carriers", "groups", "aircraft")
EDGAR_ITEM_PATTERN = re.compile(r"Item\s+(\d+\.\d+)", re.IGNORECASE)


def load_discovered(path=None):
    path = Path(path or DISCOVERED_PATH)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def write_discovered(discovered, path=None):
    Path(path or DISCOVERED_PATH).write_text(json.dumps(discovered, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def is_true(value):
    return str(value).lower() in {"1", "true", "yes"}


def source_record(row):
    """A catalog row as the dict the fetch loop and the article builder use."""
    notes = source_catalog.notes_of(row)
    types = source_registry.load_source_types()
    tier = int(row["tier"])
    type_config = types["types"].get(row["source_type"], {})
    return {
        "name": row["name"], "slug": source_catalog.source_slug(row["name"]), "url": row["url"], "discovery_urls": notes.get("discovery_urls") or [row["url"]],
        "category_hint": notes.get("category_hint", "European and other global airlines"), "source_type": row["source_type"], "official": is_true(row["official"]),
        "airline": notes.get("airline", ""), "airline_code": notes.get("airline_code", ""), "region": row["region"], "tier": tier,
        "reliability_weight": source_registry.reliability_weight_for_tier(tier), "language": row["language"], "mode": row["mode"],
        "timeout_s": int(row["timeout_s"]), "status": row["status"], "reason": row["reason"],
        "aviation_filter": bool(notes.get("aviation_filter", type_config.get("aviation_filter", False))),
        "cik": notes.get("cik", ""), "edgar_items": notes.get("edgar_items", []), "license_status": row["license_status"], "license_required": False,
    }


def catalog_feed_sources(rows, handled_names):
    """Active catalog rows that the legacy fetch loop does not already read."""
    return [source_record(row) for row in rows if row["status"] == source_catalog.STATUS_ACTIVE and row["name"] not in handled_names]


def load_aviation_filter():
    return json.loads(AVIATION_FILTER_PATH.read_text(encoding="utf-8"))


def keyword_hit(text, keywords):
    lowered = f" {str(text).lower()} "
    return any(re.search(rf"(?<![\w]){re.escape(keyword)}(?![\w])", lowered) for keyword in keywords)


def passes_aviation_filter(article, entity_index=None, config=None):
    """Whole-word aviation keyword, or a matched carrier / airline group / aircraft entity (when an index is given)."""
    config = config or load_aviation_filter()
    if keyword_hit(f"{article.get('title', '')} {article.get('description', '')}", config["keywords"]):
        return True
    entities = article.get("entities") or {}
    return any(entities.get(kind) for kind in ENTITY_KINDS_FOR_FILTER)


def filter_for_aviation(articles, entity_index):
    """Annotate with entities, then keep the items that pass the strict filter. Returns (kept, dropped_count)."""
    if not articles:
        return [], 0
    if entity_index is not None:
        try:
            from . import entities
        except ImportError:
            import entities
        entities.annotate_articles(articles, entity_index)
    config = load_aviation_filter()
    kept = [article for article in articles if passes_aviation_filter(article, entity_index, config)]
    return kept, len(articles) - len(kept)


def edgar_items_wanted(summary, wanted):
    """True when an 8-K summary lists at least one wanted item number (2.02, 7.01, 8.01)."""
    return bool(set(EDGAR_ITEM_PATTERN.findall(summary or "")) & set(wanted))


def article_from_item(item, source):
    """The article dict the pipeline uses, built from a feed item. Nothing but feed fields goes in."""
    feed_only = source["mode"] == MODE_FEED_ONLY
    published = item.published or datetime.now(timezone.utc)
    summary = item.summary[:FEED_ONLY_SUMMARY_CHARS] if feed_only else item.summary
    article = {
        "title": item.title, "link": item.link, "description": summary, "source": source["name"],
        "language": source["language"] or language.detect_language(f"{item.title} {summary}"),
        "category_hint": source["category_hint"], "source_type": source["source_type"], "official": source["official"],
        "airline": source["airline"], "airline_code": source["airline_code"], "license_required": False, "license_status": source["license_status"],
        "source_id": None, "region": source["region"], "tier": source["tier"], "reliability_weight": source["reliability_weight"],
        "topics": [], "pub_date": published.strftime("%d %b %H:%M"), "timestamp": published.timestamp(),
    }
    if feed_only:
        article["basis"] = BASIS_HEADLINE_ONLY
    return article


def read_source(source, discovered, fetcher, now, cutoff, relogger=print):
    """Fetch one catalog source through its stored feed address. Returns (articles, report).

    A stored address that fails or yields nothing verified triggers one in-memory re-discovery (logged); the stored
    file is not modified.
    """
    report = {"status": "active", "error": "", "articles": 0, "http": 0, "method": "", "rediscovered": False}
    entry = discovered.get(source["slug"])
    result = None
    if entry:
        method_items = fd.items_from_url(fetcher, entry["feed_url"])
        items = method_items[1]
        ok, _, _ = fd.validate_items(items, now) if items else (False, 0, "")
        if ok:
            result = fd.DiscoveryResult(fd.STATUS_FOUND, entry["feed_url"], method_items[0], items=items, http_code=method_items[2].status)
        else:
            relogger(f"[{source['name']}] stored feed address stopped working ({method_items[2].error or method_items[2].status}); discovering again for this run.")
            report["rediscovered"] = True
    if result is None:
        result = fd.discover(fetcher, source["discovery_urls"], now=now)
        if result.status != fd.STATUS_FOUND:
            report.update(status=result.status, error=result.reason, http=result.http_code)
            return [], report
    report.update(http=result.http_code, method=result.method)
    wanted = source["edgar_items"]
    articles = []
    for item in sorted((i for i in result.items if i.published and i.published >= cutoff), key=lambda i: i.published, reverse=True)[:MAX_ITEMS_PER_SOURCE]:
        if source["cik"] and not edgar_items_wanted(item.summary, wanted):
            continue
        articles.append(article_from_item(item, source))
    report["articles"] = len(articles)
    return articles, report


def host_of(source):
    return source_catalog.registrable_key(source["discovery_urls"][0])


def group_by_host(sources):
    """{host key: [sources]}: every list is read sequentially by one worker, different hosts in parallel."""
    groups = {}
    for source in sources:
        groups.setdefault(host_of(source), []).append(source)
    return groups
