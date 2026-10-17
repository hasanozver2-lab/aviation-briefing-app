"""Probe every catalog source and turn the result into a final status.

The probe is run by the source-probe workflow on a GitHub runner (the network there differs from a laptop's) and never
touches briefing data or the archive. It reports, per source: the discovery method, HTTP code, time, items in the last
7 days and how many of those pass the aviation filter, score above min_score and would be listed. apply_probe() then
writes the statuses, config/feeds_discovered.json and reports/source_probe.json from that verified output.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

try:
    from . import clustering, entities, feed_discovery as fd, feed_sources, market_data, source_catalog, story_lifecycle
    from .urls import canonicalize_url
except ImportError:
    import clustering
    import entities
    import feed_discovery as fd
    import feed_sources
    import market_data
    import source_catalog
    import story_lifecycle
    from urls import canonicalize_url

PROBE_TIMEOUT_SECONDS = 10
PROBE_WORKERS = 8
RECENT_DAYS = 7
FEED_METHODS = (fd.METHOD_RSS, fd.METHOD_ATOM, fd.METHOD_SITEMAP, fd.METHOD_JSONLD, fd.METHOD_HTML)
LEGACY_METHOD = "legacy_scraper"
OFFICIAL_TYPES = {"airline_ir", "regulator", "exchange", "oem"}
PRESS_TYPES = {"wire_headline", "trade"}
STOP_TOKENS = {"with", "from", "that", "this", "will", "have", "after", "airline", "airlines", "flight", "flights", "aviation", "news", "says", "their", "about"}
NEAR_MISS_MIN_SHARED = 4


def utc_now():
    return datetime.now(timezone.utc)


def suggest_status(row, result, legacy_found):
    """(status, reason) for one probed source, before the terms review is applied."""
    if result.status == fd.STATUS_FOUND:
        return source_catalog.STATUS_ACTIVE, ""
    if legacy_found:
        return source_catalog.STATUS_ACTIVE, ""
    if result.status == fd.STATUS_BLOCKED:
        return "disabled_blocked", result.reason or f"HTTP {result.http_code}"
    if result.status == fd.STATUS_ROBOTS:
        return "excluded_policy", result.reason
    if row["mode"] == "feed_only":
        return "no_public_feed", "no public RSS/Atom feed found on the publisher's site; " + result.reason
    return "no_extractable_feed", result.reason


def probe_source(row, source, builtin_by_name, discovered, now, fetch=None, legacy_fetch=None):
    """Probe one source. Returns (record, articles); articles are in the last RECENT_DAYS days and built from feed fields only."""
    fetcher = fd.PoliteFetcher(timeout=PROBE_TIMEOUT_SECONDS, **({"fetch": fetch} if fetch else {}))
    cutoff = now - timedelta(days=RECENT_DAYS)
    started = time.monotonic()
    record = {"name": row["name"], "slug": source["slug"], "host": feed_sources.host_of(source), "source_type": row["source_type"], "mode": row["mode"], "tier": int(row["tier"]),
              "legacy": row["name"] in builtin_by_name, "official": source["official"], "aviation_filter": source["aviation_filter"]}
    result = None
    stored = discovered.get(source["slug"])
    if stored:
        method, items, response = fd.items_from_url(fetcher, stored["feed_url"])
        ok, _, _ = fd.validate_items(items, now) if items else (False, 0, "")
        if ok:
            result = fd.DiscoveryResult(fd.STATUS_FOUND, stored["feed_url"], method, items=items, http_code=response.status, seconds=response.seconds)
    if result is None:
        result = fd.discover(fetcher, source["discovery_urls"], now=now)
    articles, items_7d, items_90d = [], 0, result.item_count_90d
    method = result.method if result.status == fd.STATUS_FOUND else ""
    if result.status == fd.STATUS_FOUND:
        items_7d = sum(1 for item in result.items if item.published >= cutoff)
        wanted = source["edgar_items"]
        articles = [feed_sources.article_from_item(item, source) for item in sorted(result.items, key=lambda i: i.published, reverse=True)
                    if item.published >= cutoff and not (source["cik"] and not feed_sources.edgar_items_wanted(item.summary, wanted))][:feed_sources.MAX_ITEMS_PER_SOURCE]
    legacy_found = False
    if result.status != fd.STATUS_FOUND and record["legacy"] and legacy_fetch:
        legacy_source = {**builtin_by_name[row["name"]], "timeout_s": int(row["timeout_s"]), "mode": row["mode"]}
        legacy_articles, legacy_error = legacy_fetch(legacy_source, cutoff)
        legacy_found = bool(legacy_articles)
        if legacy_found:
            method, articles, items_7d = LEGACY_METHOD, legacy_articles, len(legacy_articles)
            for article in articles:
                article["source"] = row["name"]          # a legacy article may carry the publisher named in its title
                article.setdefault("language", row["language"])
        elif legacy_error and result.status == fd.STATUS_NO_FEED:
            result = fd.DiscoveryResult(fd.STATUS_BLOCKED if "403" in legacy_error or "Timeout" in legacy_error else fd.STATUS_NO_FEED, reason=legacy_error, http_code=result.http_code)
    status, reason = suggest_status(row, result, legacy_found)
    record.update(status=status, reason=reason, method=method, feed_url=result.feed_url if result.status == fd.STATUS_FOUND else "", http_code=result.http_code,
                  seconds=round(time.monotonic() - started, 2), requests=fetcher.requests, items_7d=items_7d, items_90d=items_90d, robots=fetcher.robots_note(source["discovery_urls"][0]))
    return record, articles


def probe_all(rows, builtin_by_name, discovered, now=None, legacy_fetch=None, workers=PROBE_WORKERS):
    """Probe every row: hosts in parallel, the sources of one host strictly in turn."""
    now = now or utc_now()
    pairs = [(row, feed_sources.source_record(row)) for row in rows]
    groups = {}
    for row, source in pairs:
        groups.setdefault(feed_sources.host_of(source), []).append((row, source))

    def run_host(host_pairs):
        return [probe_source(row, source, builtin_by_name, discovered, now, legacy_fetch=legacy_fetch) for row, source in host_pairs]

    with ThreadPoolExecutor(max_workers=min(workers, len(groups) or 1)) as pool:
        results = [result for host_results in pool.map(run_host, groups.values()) for result in host_results]
    order = {row["name"]: n for n, row in enumerate(rows)}
    results.sort(key=lambda pair: order[pair[0]["name"]])
    return [record for record, _ in results], [article for _, articles in results for article in articles]


# --------------------------------------------------------------------------------------------------- yield measurement

def _title_tokens(article):
    return {token for token in "".join(c if c.isalnum() else " " for c in str(article.get("title", "")).lower()).split() if len(token) > 3 and token not in STOP_TOKENS}


def measure(articles, records, relevance_config=None):
    """Per source: items in 7 days, passing the aviation filter, in a story above min_score, and in a story that would be listed.

    Scoring is NOT changed: stories are scored exactly as the daily pipeline scores them. Returns (records, clusters, near_misses).
    """
    relevance = relevance_config or story_lifecycle.load_relevance_config()
    min_score = relevance["selection"]["min_score"]
    by_name = {record["name"]: record for record in records}
    for record in records:
        record.update(aviation_passed=0, above_min_score=0, listed=0)
    if not articles:
        return records, [], []
    index = entities.EntityIndex.from_csv()
    config = feed_sources.load_aviation_filter()
    needs_filter = {record["name"] for record in records if record.get("aviation_filter")}
    kept = []
    for article in articles:
        result = market_data.classify_event_type(article["title"], article.get("description", ""))
        article["event_type"], article["event_weight"] = (result["event_type"], result["event_weight"]) if result else (None, None)
    entities.annotate_articles(articles, index)
    for article in articles:
        record = by_name[article["source"]]
        if article["source"] in needs_filter and not feed_sources.passes_aviation_filter(article, index, config):
            continue
        record["aviation_passed"] += 1
        kept.append(article)
    groups = clustering.cluster_articles(kept)
    representatives = story_lifecycle.cluster_representatives(kept)
    candidates = [_candidate(article, number) for number, article in enumerate(representatives, start=1)]
    story_lifecycle.enrich_stories(candidates, kept, relevance)
    story_by_link = {canonicalize_url(c["original_source"]["url"]): c for c in candidates}
    clusters = []
    for group in groups:
        members = [kept[i] for i in group]
        rep = max(members, key=lambda a: (a.get("reliability_weight") or 0, bool(a.get("official")), -a.get("timestamp", 0)))
        story = story_by_link.get(canonicalize_url(rep["link"]))
        if story is None:
            continue
        above = float(story["relevance_score"]) >= min_score
        listed = above and not story_lifecycle.is_excluded(story, relevance)
        for member in members:
            by_name[member["source"]]["above_min_score"] += above
            by_name[member["source"]]["listed"] += listed
        distinct = {m["source"] for m in members}
        if len(distinct) > 1:
            clusters.append({"story_id": story["story_id"], "headline": story["headline"], "score": story["relevance_score"], "listed": bool(listed),
                             "sources": [{"name": m["source"], "type": m["source_type"], "title": m["title"], "link": m["link"]} for m in sorted(members, key=lambda m: m["source"])],
                             "mixed_official_and_press": bool({m["source_type"] for m in members} & OFFICIAL_TYPES and {m["source_type"] for m in members} & PRESS_TYPES)})
    clusters.sort(key=lambda c: (-len({s["name"] for s in c["sources"]}), -c["score"]))
    near = _near_misses(kept, groups)
    return records, clusters[:40], near


def _candidate(article, number):
    try:
        from . import _engine
    except ImportError:
        import _engine
    return _engine.build_candidate_story(article, number)


def _near_misses(articles, groups):
    """Pairs from different sources that share at least NEAR_MISS_MIN_SHARED distinctive title words yet stayed in different stories."""
    group_of = {i: g for g, members in enumerate(groups) for i in members}
    tokens = [_title_tokens(article) for article in articles]
    found = []
    for i in range(len(articles)):
        for j in range(i + 1, len(articles)):
            if articles[i]["source"] == articles[j]["source"] or group_of[i] == group_of[j]:
                continue
            shared = tokens[i] & tokens[j]
            if len(shared) >= NEAR_MISS_MIN_SHARED:
                found.append({"shared": sorted(shared), "a": {"source": articles[i]["source"], "title": articles[i]["title"]}, "b": {"source": articles[j]["source"], "title": articles[j]["title"]}})
    found.sort(key=lambda pair: -len(pair["shared"]))
    return found[:20]


# --------------------------------------------------------------------------------------------------- applying a probe

def apply_probe(rows, probe, terms_review, discovered, now=None):
    """Final statuses from a verified probe. Returns (rows, discovered, changes).

    Terms review: commercial_use_risk is recorded for every source. A source is excluded only where the terms explicitly forbid
    automated reading of the feed AND it is a press/data (feed_only) or exchange source; robots.txt exclusions come from the probe.
    """
    now = now or utc_now()
    stamp = now.isoformat(timespec="seconds")
    by_name = {record["name"]: record for record in probe["sources"]}
    terms = terms_review["sources"]
    discovered = dict(discovered)
    changes = []
    for row in rows:
        record = by_name.get(row["name"])
        if record is None:
            raise ValueError(f"no probe result for {row['name']}: every source needs a final status")
        status, reason = record["status"], record["reason"]
        review = terms.get(row["name"], {})
        if review.get("automated_reading_forbidden") and (row["mode"] == "feed_only" or row["source_type"] == "exchange") and status != "excluded_policy":
            status = "excluded_policy"
            reason = f"terms forbid automated reading: \"{review['quote'][:200]}\" ({review['terms_url'] or 'robots.txt'})"
        row["commercial_use_risk"] = review.get("commercial_use_risk", row.get("commercial_use_risk", ""))
        previous = row["status"]
        row["status"], row["reason"], row["active"] = status, reason, "1" if status == source_catalog.STATUS_ACTIVE else "0"
        slug = source_catalog.source_slug(row["name"])
        if status == source_catalog.STATUS_ACTIVE and record["method"] in FEED_METHODS:
            row["timeout_s"] = str(max(int(row["timeout_s"]), PROBE_TIMEOUT_SECONDS))
            row["feed_url"] = record["feed_url"]
            kept = discovered.get(slug, {})
            discovered[slug] = {"feed_url": record["feed_url"], "method": record["method"], "verified_at": stamp, "last_ok_at": stamp, "item_count_90d": record["items_90d"],
                                **({"first_verified_at": kept["first_verified_at"]} if "first_verified_at" in kept else {})}
        else:
            discovered.pop(slug, None)
        if previous != status:
            changes.append((row["name"], previous, status, reason))
    return rows, discovered, changes
