"""Weekly retry of sources that are disabled_blocked.

Every disabled_blocked source gets ONE content request per RETRY_INTERVAL_DAYS inside the daily pipeline (plus the robots.txt
read that obeying robots needs). The attempt is valid when the answer is readable content with at least one dated item from
the last 90 days; the source is then active again (recorded in status.json, with the address that worked) and is read like any
other source from the next collection on. The last attempt time is kept in status.json. A retry never fails the run.
"""

from datetime import datetime, timedelta, timezone

try:
    from . import feed_discovery as fd, feed_sources, source_catalog
except ImportError:
    import feed_discovery as fd
    import feed_sources
    import source_catalog

RETRY_INTERVAL_DAYS = 7
RETRY_TIMEOUT_SECONDS = 10
STATUS_BLOCKED = "disabled_blocked"


def utc_now():
    return datetime.now(timezone.utc)


def is_due(previous_entry, now):
    """True when the source has never been retried or its last attempt is at least RETRY_INTERVAL_DAYS old."""
    last = fd.parse_datetime((previous_entry or {}).get("last_retry_at"))
    return last is None or now - last >= timedelta(days=RETRY_INTERVAL_DAYS)


def has_valid_content(items, now):
    """At least one item with a title, a link and a date from the last 90 days (not every item has to be complete)."""
    window = timedelta(days=fd.VALID_WINDOW_DAYS)
    return any(item.title and item.link and item.published and now - item.published <= window for item in items)


def target_url(row, source, discovered):
    stored = discovered.get(source["slug"])
    return stored["feed_url"] if stored else (row["feed_url"] if row["feed_url"] and row["feed_url"] != row["url"] else source["discovery_urls"][0])


def retry_one(row, source, discovered, now, fetch=None):
    """One attempt. Returns {valid, method, feed_url, reason, http}."""
    url = target_url(row, source, discovered)
    fetcher = fd.PoliteFetcher(timeout=max(source["timeout_s"], RETRY_TIMEOUT_SECONDS), **({"fetch": fetch} if fetch else {}))
    if not fetcher.allowed(url):
        return {"valid": False, "method": "", "feed_url": "", "http": 0, "reason": "robots.txt disallows this address"}
    response = fetcher.get(url)
    if response.status != 200:
        return {"valid": False, "method": "", "feed_url": "", "http": response.status, "reason": response.error or f"HTTP {response.status}"}
    method, items = fd.classify_body(response.body, response.final_url or url)
    allowed = feed_sources.allowed_methods(source)
    if method and method != "sitemap_index" and (allowed is None or method in allowed) and has_valid_content(items, now):
        return {"valid": True, "method": method, "feed_url": url, "http": 200, "reason": ""}
    return {"valid": False, "method": method or "", "feed_url": "", "http": 200,
            "reason": "reachable (HTTP 200) but no readable dated items in one request; the probe workflow does the full discovery"}


def retry_blocked(rows, previous_status, overrides, now=None, discovered=None, fetch=None, log=print):
    """{source name: result} for the blocked sources that are due; nothing else is touched. Never raises."""
    now = now or utc_now()
    discovered = feed_sources.load_discovered() if discovered is None else discovered
    previous = (previous_status or {}).get("sources", {})
    skipped = {name for name, decision in (overrides or {}).get("sources", {}).items() if decision.get("no_retry")}
    results = {}
    for row in rows:
        if row["status"] != STATUS_BLOCKED or row["name"] in skipped or not is_due(previous.get(row["name"]), now):
            continue
        try:
            result = retry_one(row, feed_sources.source_record(row), discovered, now, fetch)
        except Exception as exc:
            result = {"valid": False, "method": "", "feed_url": "", "http": 0, "reason": f"retry error: {type(exc).__name__}"}
        result["at"] = now.isoformat(timespec="seconds")
        results[row["name"]] = result
        log(f"[{row['name']}] weekly retry: " + ("valid content, source is active again" if result["valid"] else f"still blocked ({result['reason']})"))
    return results


def recovered_sources(previous_status, retry_results):
    """{name: {feed_url, method}} for every source that is active again, from this run's retries and from status.json."""
    recovered = {name: {"feed_url": entry["retry_feed"]["feed_url"], "method": entry["retry_feed"]["method"]}
                 for name, entry in (previous_status or {}).get("sources", {}).items() if entry.get("retry_feed") and entry.get("status") in ("active", "error")}
    for name, result in (retry_results or {}).items():
        if result["valid"]:
            recovered[name] = {"feed_url": result["feed_url"], "method": result["method"]}
    return recovered
