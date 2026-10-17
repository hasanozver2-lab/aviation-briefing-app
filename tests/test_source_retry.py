import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from api import _engine, feed_discovery as fd, feed_sources, source_catalog, source_retry
from scripts import run_pipeline

NOW = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
RECENT = (NOW - timedelta(days=2)).strftime("%a, %d %b %Y %H:%M:%S +0000")
OLD = (NOW - timedelta(days=200)).strftime("%a, %d %b %Y %H:%M:%S +0000")
WEEK = timedelta(days=7)


def rss(items, date=RECENT):
    body = "".join(f"<item><title>{t}</title><link>{l}</link><pubDate>{date}</pubDate><description>s</description></item>" for t, l in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'.encode()


GOOD = rss([("Airline X opens a new base in Lisbon", "https://blocked.example/a1")])


class Site:
    def __init__(self, pages):
        self.pages, self.log = pages, []

    def __call__(self, url, headers, timeout):
        self.log.append(url)
        status, body = self.pages.get(url, (404, b""))
        return fd.Response(status, body, {}, url, 0.01, "" if status == 200 else f"HTTPError {status}")


def row(name="Blocked Source", **overrides):
    base = {"name": name, "url": "https://blocked.example/feed", "feed_url": "", "feed_type": "rss", "region": "Global", "tier": "1", "license_status": "public", "language": "en",
            "active": "0", "notes": json.dumps({"discovery_urls": ["https://blocked.example/feed"]}), "source_type": "airline_ir", "official": "true", "mode": "full",
            "timeout_s": "10", "status": "disabled_blocked", "reason": "HTTPError 403", "commercial_use_risk": ""}
    base.update(overrides)
    return base


def retry(rows, previous=None, overrides=None, pages=None, now=NOW):
    site = Site(pages if pages is not None else {"https://blocked.example/feed": (200, GOOD)})
    logs = []
    results = source_retry.retry_blocked(rows, previous, overrides, now, discovered={}, fetch=site, log=logs.append)
    return results, site, logs


def content_requests(site):
    return [url for url in site.log if not url.endswith("/robots.txt")]


# --- when a source is due --------------------------------------------------------------------------------------------------

def test_never_retried_or_a_week_old_is_due_and_younger_is_not():
    assert source_retry.is_due(None, NOW) and source_retry.is_due({}, NOW)
    assert source_retry.is_due({"last_retry_at": (NOW - WEEK).isoformat()}, NOW)
    assert not source_retry.is_due({"last_retry_at": (NOW - WEEK + timedelta(minutes=1)).isoformat()}, NOW)


def test_only_blocked_due_sources_are_attempted():
    rows = [row("A Blocked"), row("B Active", status="active", active="1"), row("C Excluded", status="excluded_policy"), row("D Recent")]
    previous = {"sources": {"D Recent": {"last_retry_at": (NOW - timedelta(days=2)).isoformat()}}}
    results, _, _ = retry(rows, previous)
    assert list(results) == ["A Blocked"]


def test_a_source_marked_no_retry_is_never_attempted():
    results, site, _ = retry([row("SEC Like")], overrides={"sources": {"SEC Like": {"status": "disabled_blocked", "reason": "needs contact", "no_retry": True}}})
    assert results == {} and site.log == []


# --- one request ------------------------------------------------------------------------------------------------------------

def test_a_retry_makes_exactly_one_content_request():
    results, site, _ = retry([row()])
    assert len(content_requests(site)) == 1 and results["Blocked Source"]["valid"] is True


def test_valid_content_means_readable_items_with_a_recent_date():
    results, _, logs = retry([row()])
    result = results["Blocked Source"]
    assert result == {"valid": True, "method": "rss", "feed_url": "https://blocked.example/feed", "http": 200, "reason": "", "at": NOW.isoformat(timespec="seconds")}
    assert "source is active again" in logs[0]


def test_content_with_nothing_in_the_last_90_days_is_not_valid():
    results, _, _ = retry([row()], pages={"https://blocked.example/feed": (200, rss([("Old story", "https://blocked.example/o")], OLD))})
    assert results["Blocked Source"]["valid"] is False


def test_a_still_blocked_source_stays_blocked_with_the_reason():
    results, _, logs = retry([row()], pages={"https://blocked.example/feed": (403, b"")})
    assert results["Blocked Source"]["valid"] is False and results["Blocked Source"]["http"] == 403 and "still blocked" in logs[0]


def test_robots_txt_is_still_obeyed():
    results, site, _ = retry([row()], pages={"https://blocked.example/robots.txt": (200, b"User-agent: *\nDisallow: /"), "https://blocked.example/feed": (200, GOOD)})
    assert results["Blocked Source"]["valid"] is False and "robots" in results["Blocked Source"]["reason"] and content_requests(site) == []


def test_a_feed_only_source_needs_an_rss_or_atom_answer_not_a_page():
    sitemap = (f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="{fd.NEWS_SITEMAP_NS}"><url><loc>https://blocked.example/n</loc><news:news>'
               f'<news:publication_date>{(NOW - timedelta(days=1)).isoformat()}</news:publication_date><news:title>Airline signs deal</news:title></news:news></url></urlset>').encode()
    results, _, _ = retry([row(mode="feed_only")], pages={"https://blocked.example/feed": (200, sitemap)})
    assert results["Blocked Source"]["valid"] is False
    results, _, _ = retry([row(mode="full")], pages={"https://blocked.example/feed": (200, sitemap)})
    assert results["Blocked Source"]["valid"] is True and results["Blocked Source"]["method"] == "sitemap"


def test_a_page_that_answers_but_has_no_feed_is_reported_as_reachable_not_valid():
    results, _, _ = retry([row()], pages={"https://blocked.example/feed": (200, b"<html></html>")})
    assert results["Blocked Source"]["valid"] is False and "HTTP 200" in results["Blocked Source"]["reason"]


def test_a_crash_inside_the_retry_is_contained():
    def boom(url, headers, timeout):
        raise RuntimeError("transport exploded")
    results = source_retry.retry_blocked([row()], None, None, NOW, discovered={}, fetch=boom, log=lambda m: None)
    assert results["Blocked Source"]["valid"] is False


def test_recovered_sources_come_from_this_runs_retries_and_from_status_json():
    previous = {"sources": {"Old Recovery": {"status": "active", "retry_feed": {"feed_url": "https://o.example/feed", "method": "rss"}},
                            "Failed Again": {"status": "disabled_blocked", "retry_feed": {"feed_url": "https://f.example/feed", "method": "rss"}}}}
    results = {"New Recovery": {"valid": True, "feed_url": "https://n.example/feed", "method": "atom"}, "Still Blocked": {"valid": False}}
    recovered = source_retry.recovered_sources(previous, results)
    assert set(recovered) == {"Old Recovery", "New Recovery"} and recovered["New Recovery"]["method"] == "atom"


# --- status.json and the pipeline -----------------------------------------------------------------------------------------------

def test_status_json_records_the_attempt_time_the_result_and_the_recovery(monkeypatch):
    monkeypatch.setattr(source_catalog, "read_rows", lambda path=None: [])
    report = {"Back Again": {"status": "active", "error": "", "articles": 2, "articles_24h": 2}, "Still Down": {"status": "disabled_blocked", "error": "HTTPError 403", "articles": 0}}
    attempts = {"Back Again": {"valid": True, "feed_url": "https://b.example/feed", "method": "rss", "at": "2026-10-20T09:00:00+00:00", "reason": ""},
                "Still Down": {"valid": False, "feed_url": "", "method": "", "at": "2026-10-20T09:00:00+00:00", "reason": "HTTP 403"}}
    health = run_pipeline.source_health(report, None, NOW, attempts)
    assert health["Back Again"]["status"] == "active" and health["Back Again"]["retry_feed"] == {"feed_url": "https://b.example/feed", "method": "rss"} and health["Back Again"]["recovered_at"]
    assert health["Still Down"]["status"] == "disabled_blocked" and health["Still Down"]["last_retry_at"] == "2026-10-20T09:00:00+00:00" and health["Still Down"]["retry_note"] == "HTTP 403"
    later = run_pipeline.source_health(report, {"sources": health}, NOW + timedelta(days=1), None)
    assert later["Still Down"]["last_retry_at"] == "2026-10-20T09:00:00+00:00", "the last attempt time survives runs that do not retry"
    assert later["Back Again"]["retry_feed"]["feed_url"] == "https://b.example/feed"


def quiet(stories, *a, **k):
    return {"calls": 0, "narrated": 0, "pending": 0, "error": ""}


def story(name):
    from api import story_lifecycle
    url = f"https://example.com/{name}"
    story_id = story_lifecycle.stable_story_id(url)
    return {"id": story_id, "story_id": story_id, "section": "Route news", "region_section": "Europe", "headline": name, "event_type": None, "relevance_score": 70, "narrative_status": "pending",
            "lead": "l", "original_source": {"url": url, "title": name, "source_name": "Wire"}, "sources": [{"name": "Wire", "url": url, "title": name}], "source_count": 1,
            "published_at_iso": story_lifecycle.to_iso(NOW - timedelta(hours=1))}


def test_the_pipeline_retries_once_a_week_logs_it_and_hands_recovered_sources_to_the_collection(tmp_path, monkeypatch):
    rows = [row()]
    monkeypatch.setattr(source_catalog, "read_rows", lambda path=None: rows)
    calls, seen_recovered = [], []
    site = Site({"https://blocked.example/feed": (200, GOOD)})
    real_retry = source_retry.retry_blocked

    def spy(rows_, previous, overrides, now, *a, **kw):
        calls.append(now)
        return real_retry(rows_, previous, overrides, now, discovered={}, fetch=site, log=lambda m: None)

    monkeypatch.setattr(source_retry, "retry_blocked", spy)

    def collect(recovered=None):
        seen_recovered.append(dict(recovered or {}))
        return {"stories": [story("Alpha")], "articles": 3, "candidates": 1, "market": {"status": "ok", "items": [], "events": []},
                "source_report": {"Blocked Source": {"status": "active", "error": "", "articles": 1, "articles_24h": 1}}}

    monkeypatch.setattr(_engine, "collect_run", collect)
    assert run_pipeline.run(out_dir=tmp_path, now=NOW, api_key="", narrate=quiet) == 0
    status = json.loads((tmp_path / "briefings/status.json").read_text(encoding="utf-8"))
    entry = status["sources"]["Blocked Source"]
    assert entry["last_retry_at"] == NOW.isoformat(timespec="seconds") and entry["retry_feed"]["feed_url"] == "https://blocked.example/feed" and entry["status"] == "active"
    assert seen_recovered == [{"Blocked Source": {"feed_url": "https://blocked.example/feed", "method": "rss"}}]

    run_pipeline.run(out_dir=tmp_path, now=NOW + timedelta(days=2), api_key="", narrate=quiet)
    assert len(calls) == 2 and len(content_requests(site)) == 1, "the second run two days later made no new request"
    assert seen_recovered[1] == seen_recovered[0], "a recovered source keeps being read from status.json"


def test_a_retry_that_blows_up_never_fails_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr(source_retry, "retry_blocked", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("retry broke")))
    monkeypatch.setattr(source_catalog, "read_rows", lambda path=None: [])
    monkeypatch.setattr(_engine, "collect_run", lambda: {"stories": [story("Alpha")], "articles": 3, "candidates": 1, "market": {"status": "ok", "items": [], "events": []}, "source_report": {}})
    assert run_pipeline.run(out_dir=tmp_path, now=NOW, api_key="", narrate=quiet) == 0


def test_the_collection_reads_a_recovered_catalog_source_from_its_retry_address(monkeypatch):
    rows = [row("Recovered Wire", url="https://wire.example/", notes=json.dumps({"discovery_urls": ["https://wire.example/"]}))]
    monkeypatch.setattr(source_catalog, "read_rows", lambda path=None: rows)
    monkeypatch.setattr(feed_sources, "load_discovered", lambda path=None: {})
    monkeypatch.setattr(_engine, "get_builtin_source_records", lambda max_hours=48: [])
    site = Site({"https://wire.example/retry-feed": (200, rss([("Airline X orders aircraft", "https://wire.example/a1")]))})
    original = fd.PoliteFetcher
    monkeypatch.setattr(_engine.feed_discovery, "PoliteFetcher", lambda **kw: original(fetch=site, sleep=lambda s: None))
    monkeypatch.setattr(feed_sources, "filter_for_aviation", lambda items, index: (items, 0))
    report = {}
    articles = _engine._read_catalog_feeds(NOW - timedelta(days=30), report, recovered={"Recovered Wire": {"feed_url": "https://wire.example/retry-feed", "method": "rss"}})
    assert [a["title"] for a in articles] == ["Airline X orders aircraft"] and report["Recovered Wire"]["status"] == "active"
    assert site.log == ["https://wire.example/retry-feed"]
    report = {}
    assert _engine._read_catalog_feeds(NOW - timedelta(days=30), report) == [] and report["Recovered Wire"]["status"] == "disabled_blocked", "without the recovery it stays blocked"
