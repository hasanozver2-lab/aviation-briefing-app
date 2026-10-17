import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from api import feed_discovery as fd, feed_sources, source_catalog, source_probe

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
RECENT = (NOW - timedelta(hours=5)).strftime("%a, %d %b %Y %H:%M:%S +0000")
PROJECT = Path(__file__).resolve().parents[1]
TERMS = json.loads((PROJECT / "config" / "source_terms_review.json").read_text(encoding="utf-8"))
REAL_FETCHER = fd.PoliteFetcher


def rss(items):
    body = "".join(f"<item><title>{t}</title><link>{l}</link><pubDate>{RECENT}</pubDate><description>summary</description></item>" for t, l in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'.encode()


class Site:
    def __init__(self, pages):
        self.pages, self.log = pages, []

    def __call__(self, url, headers, timeout):
        self.log.append(url)
        status, body = self.pages.get(url, (404, b""))
        if isinstance(body, str):
            body = body.encode()
        return fd.Response(status, body, {}, url, 0.01, "" if status == 200 else f"HTTPError {status}")


def row(name="Wire Example", **overrides):
    base = {"name": name, "url": "https://wire.example/", "feed_url": "", "feed_type": "rss", "region": "Global", "tier": "3", "license_status": "public", "language": "en",
            "active": "0", "notes": json.dumps({"discovery_urls": ["https://wire.example/"]}), "source_type": "wire_headline", "official": "false", "mode": "feed_only",
            "timeout_s": "3", "status": "no_extractable_feed", "reason": "not probed yet", "commercial_use_risk": ""}
    base.update(overrides)
    return base


def probe_one(pages, monkeypatch, legacy=None, discovered=None, **overrides):
    r = row(**overrides)
    site = Site(pages)
    monkeypatch.setattr(fd, "PoliteFetcher", lambda **kw: REAL_FETCHER(fetch=site, sleep=lambda s: None, **{k: v for k, v in kw.items() if k != "fetch"}))
    builtin = {r["name"]: {"name": r["name"], "url": r["url"]}} if legacy is not None else {}
    return source_probe.probe_source(r, feed_sources.source_record(r), builtin, discovered or {}, NOW, legacy_fetch=legacy)


FEED = rss([("Airline X opens new route", "https://wire.example/a1"), ("Airline Y orders aircraft", "https://wire.example/a2")])
HOME = b"<html></html>"


# --- statuses ----------------------------------------------------------------------------------------------------------

def test_a_verified_feed_makes_the_source_active_and_counts_its_recent_items(monkeypatch):
    record, articles = probe_one({"https://wire.example/": (200, HOME), "https://wire.example/feed": (200, FEED)}, monkeypatch)
    assert (record["status"], record["method"], record["items_7d"], len(articles)) == ("active", "rss", 2, 2)
    assert record["feed_url"] == "https://wire.example/feed" and record["http_code"] == 200 and record["seconds"] >= 0


def test_a_403_is_disabled_blocked_with_the_http_code_in_the_reason(monkeypatch):
    record, _ = probe_one({"https://wire.example/": (403, b"")}, monkeypatch)
    assert record["status"] == "disabled_blocked" and "403" in record["reason"] and record["http_code"] == 403


def test_a_robots_exclusion_is_excluded_policy_with_the_rule(monkeypatch):
    record, _ = probe_one({"https://wire.example/robots.txt": (200, "User-agent: *\nDisallow: /"), "https://wire.example/": (200, HOME)}, monkeypatch)
    assert record["status"] == "excluded_policy" and "robots.txt disallows" in record["reason"]


def test_no_feed_on_a_press_source_is_no_public_feed_and_on_a_web_source_no_extractable_feed(monkeypatch):
    pages = {"https://wire.example/": (200, HOME)}
    assert probe_one(pages, monkeypatch)[0]["status"] == "no_public_feed"
    web, _ = probe_one(pages, monkeypatch, mode="full", source_type="airline_ir")
    assert web["status"] == "no_extractable_feed"


def test_a_legacy_scraper_that_still_returns_articles_keeps_the_source_active(monkeypatch):
    article = {"title": "Carrier press release about winter schedule", "link": "https://wire.example/n1", "source": "Some Publisher", "timestamp": NOW.timestamp(), "description": ""}
    record, articles = probe_one({"https://wire.example/": (200, HOME)}, monkeypatch, legacy=lambda source, cutoff: ([dict(article)], ""), mode="full", source_type="airline_ir")
    assert record["status"] == "active" and record["method"] == "legacy_scraper" and articles[0]["source"] == "Wire Example"


def test_a_legacy_source_blocked_on_both_paths_is_blocked_not_silently_dropped(monkeypatch):
    record, _ = probe_one({"https://wire.example/": (200, HOME)}, monkeypatch, legacy=lambda source, cutoff: ([], "HTTPError 403"), mode="full", source_type="airline_ir")
    assert record["status"] == "disabled_blocked" and "403" in record["reason"]


def test_a_stored_feed_is_reverified_first(monkeypatch):
    stored = {"wire_example": {"feed_url": "https://wire.example/stored.xml", "method": "rss"}}
    record, _ = probe_one({"https://wire.example/stored.xml": (200, FEED)}, monkeypatch, discovered=stored)
    assert record["status"] == "active" and record["feed_url"] == "https://wire.example/stored.xml"


# --- measurement ---------------------------------------------------------------------------------------------------------

def test_yield_is_measured_without_touching_scoring():
    records = [{"name": "Airline Newsroom", "source_type": "airline_ir", "aviation_filter": False}, {"name": "Wire Example", "source_type": "wire_headline", "aviation_filter": True}]

    def article(title, source, source_type, tier, official, weight):
        return {"title": title, "link": f"https://x.example/{abs(hash((title, source)))}", "description": "", "source": source, "source_type": source_type, "official": official,
                "tier": tier, "reliability_weight": weight, "timestamp": NOW.timestamp(), "language": "en", "region": "Global", "airline": "", "topics": [], "pub_date": "",
                "license_status": "public"}

    articles = [article("Lufthansa places firm order for 20 Airbus A350 aircraft", "Airline Newsroom", "airline_ir", 1, True, 1.0),
                article("Lufthansa places firm order for 20 Airbus A350 aircraft", "Wire Example", "wire_headline", 3, False, 0.7),
                article("Central bank holds interest rates steady", "Wire Example", "wire_headline", 3, False, 0.7)]
    out, clusters, _ = source_probe.measure(articles, records)
    by_name = {r["name"]: r for r in out}
    assert by_name["Wire Example"]["aviation_passed"] == 1, "the general-news item is dropped by the filter"
    assert by_name["Airline Newsroom"]["aviation_passed"] == 1 and by_name["Airline Newsroom"]["above_min_score"] == 1
    assert len(clusters) == 1 and {s["name"] for s in clusters[0]["sources"]} == {"Airline Newsroom", "Wire Example"} and clusters[0]["mixed_official_and_press"]


# --- applying a probe -------------------------------------------------------------------------------------------------------

def probe_doc(**record):
    base = {"name": "Wire Example", "status": "active", "reason": "", "method": "rss", "feed_url": "https://wire.example/feed", "items_90d": 12}
    base.update(record)
    return {"sources": [base]}


def terms(**review):
    return {"sources": {"Wire Example": {"commercial_use_risk": "high", "terms_url": "https://wire.example/terms", "quote": "", "automated_reading_forbidden": False, **review}}}


def test_a_probed_feed_is_stored_with_its_method_time_and_activates_the_row():
    rows, discovered, changes = source_probe.apply_probe([row()], probe_doc(), terms(), {}, NOW)
    assert rows[0]["status"] == "active" and rows[0]["active"] == "1" and rows[0]["commercial_use_risk"] == "high" and int(rows[0]["timeout_s"]) >= 10
    stamp = NOW.isoformat(timespec="seconds")
    assert discovered["wire_example"] == {"feed_url": "https://wire.example/feed", "method": "rss", "verified_at": stamp, "last_ok_at": stamp, "item_count_90d": 12}
    assert changes[0][:3] == ("Wire Example", "no_extractable_feed", "active")


def test_high_commercial_risk_never_deactivates_a_source():
    rows, _, _ = source_probe.apply_probe([row()], probe_doc(), terms(commercial_use_risk="high"), {}, NOW)
    assert rows[0]["status"] == "active"


def test_explicit_terms_against_automated_reading_exclude_a_press_source_with_the_quote():
    rows, discovered, _ = source_probe.apply_probe([row()], probe_doc(), terms(automated_reading_forbidden=True, quote="you may not use any robot or bot"),
                                                   {"wire_example": {"feed_url": "x"}}, NOW)
    assert rows[0]["status"] == "excluded_policy" and rows[0]["active"] == "0" and "you may not use any robot or bot" in rows[0]["reason"] and "wire_example" not in discovered


def test_the_same_terms_do_not_exclude_an_airline_newsroom_only_record_the_risk():
    rows, _, _ = source_probe.apply_probe([row(mode="full", source_type="airline_ir")], probe_doc(), terms(automated_reading_forbidden=True, quote="no robots"), {}, NOW)
    assert rows[0]["status"] == "active" and rows[0]["commercial_use_risk"] == "high"


def test_exchange_sources_follow_the_exclusion_rule_too():
    rows, _, _ = source_probe.apply_probe([row(mode="full", source_type="exchange")], probe_doc(), terms(automated_reading_forbidden=True, quote="bars any bot"), {}, NOW)
    assert rows[0]["status"] == "excluded_policy"


def test_a_source_without_a_probe_result_is_an_error_so_none_is_skipped_silently():
    with pytest.raises(ValueError, match="no probe result"):
        source_probe.apply_probe([row("Unprobed")], probe_doc(), terms(), {}, NOW)


def test_a_failed_source_loses_its_stored_feed_and_gets_the_probe_reason():
    rows, discovered, _ = source_probe.apply_probe([row(status="active", active="1")], probe_doc(status="disabled_blocked", reason="HTTPError 403 on /", method="", feed_url=""),
                                                   terms(), {"wire_example": {"feed_url": "https://wire.example/feed"}}, NOW)
    assert rows[0]["status"] == "disabled_blocked" and rows[0]["reason"] == "HTTPError 403 on /" and discovered == {}


# --- the repository's own data and workflow -----------------------------------------------------------------------------------

def test_the_terms_review_covers_every_catalog_source_and_marks_what_was_not_read():
    names = {r["name"] for r in source_catalog.read_rows()}
    assert names == set(TERMS["sources"])
    for name, review in TERMS["sources"].items():
        assert review["commercial_use_risk"] in {"low", "medium", "high"}
        if review["automated_reading_forbidden"]:
            assert review["quote"], f"{name}: an exclusion needs a quote"
        if not review["read"]:
            assert review["commercial_use_risk"] != "low" or name.startswith("SEC EDGAR"), f"{name}: an unread page cannot support 'low' on its own"


def test_the_probe_workflow_is_manual_read_only_and_cannot_touch_briefing_data():
    text = (PROJECT / ".github" / "workflows" / "source-probe.yml").read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert "workflow_dispatch:" in code and "schedule" not in code and "push:" not in code
    assert "contents: read" in code and "contents: write" not in code
    assert "secrets." not in code and "briefing-data" not in code and "git push" not in code and "run_pipeline" not in code
    assert "upload-artifact" in code and "scripts/probe_sources.py" in code


# --- method restriction and the legacy path ---------------------------------------------------------------------------------

NEWS_SITEMAP = (f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="{fd.NEWS_SITEMAP_NS}"><url><loc>https://wire.example/n1</loc>'
                f'<news:news><news:publication_date>{(NOW - timedelta(hours=3)).isoformat()}</news:publication_date><news:title>Airline signs engine deal</news:title></news:news></url></urlset>')


def test_a_feed_only_source_may_not_fall_back_to_a_sitemap(monkeypatch):
    pages = {"https://wire.example/": (200, HOME), "https://wire.example/news-sitemap.xml": (200, NEWS_SITEMAP)}
    record, _ = probe_one(pages, monkeypatch)
    assert record["status"] == "no_public_feed" and record["method"] == ""


def test_a_web_source_may_use_a_news_sitemap(monkeypatch):
    pages = {"https://wire.example/": (200, HOME), "https://wire.example/news-sitemap.xml": (200, NEWS_SITEMAP)}
    record, _ = probe_one(pages, monkeypatch, mode="full", source_type="airline_ir")
    assert record["status"] == "active" and record["method"] == "sitemap"


def test_a_stored_sitemap_address_is_not_kept_for_a_feed_only_source():
    rows, discovered, _ = source_probe.apply_probe([row()], probe_doc(method="sitemap", feed_url="https://wire.example/news-sitemap.xml"), terms(), {}, NOW)
    assert discovered == {} and rows[0]["feed_url"] == ""


def test_the_legacy_path_obeys_robots_txt(monkeypatch):
    pages = {"https://wire.example/robots.txt": (200, "User-agent: *\nDisallow: /"), "https://wire.example/": (200, HOME)}
    record, _ = probe_one(pages, monkeypatch, legacy=lambda source, cutoff: ([{"title": "x" * 30, "link": "l", "source": "s", "timestamp": NOW.timestamp()}], ""), mode="full", source_type="airline_ir")
    assert record["status"] == "excluded_policy" and "robots.txt disallows" in record["reason"]


def test_a_quiet_legacy_rss_source_that_answered_is_working_but_a_silent_html_scraper_is_not(monkeypatch):
    pages = {"https://wire.example/": (200, HOME)}
    quiet_rss, _ = probe_one(pages, monkeypatch, legacy=lambda source, cutoff: ([], ""), mode="full", source_type="airline_ir")
    assert quiet_rss["status"] == "active" and quiet_rss["method"] == "legacy_scraper"
    original = fd.PoliteFetcher
    r = row(mode="full", source_type="airline_ir")
    site = Site(pages)
    monkeypatch.setattr(fd, "PoliteFetcher", lambda **kw: REAL_FETCHER(fetch=site, sleep=lambda s: None, **{k: v for k, v in kw.items() if k != "fetch"}))
    record, _ = source_probe.probe_source(r, feed_sources.source_record(r), {r["name"]: {"name": r["name"], "url": r["url"], "fetch_mode": "html"}}, {}, NOW, legacy_fetch=lambda s, c: ([], ""))
    assert record["status"] == "no_extractable_feed"


OVERRIDES = json.loads((PROJECT / "config" / "source_status_overrides.json").read_text(encoding="utf-8"))


def test_a_decision_by_a_person_wins_over_the_probe_result():
    rows, _, _ = source_probe.apply_probe([row()], probe_doc(), terms(), {}, NOW, overrides={"sources": {"Wire Example": {"status": "excluded_policy", "reason": "terms forbid it (https://x)"}}})
    assert rows[0]["status"] == "excluded_policy" and rows[0]["active"] == "0" and rows[0]["reason"] == "terms forbid it (https://x)"


def test_the_recorded_overrides_are_the_agreed_ones():
    sources = OVERRIDES["sources"]
    for name in ("Air Canada News Releases", "Textron Aviation Newsroom"):
        assert sources[name]["status"] == "excluded_policy" and "http" in sources[name]["reason"] and "robots" in sources[name]["reason"].lower() or "automated" in sources[name]["reason"].lower()
    sec = [name for name in sources if name.startswith("SEC EDGAR")]
    assert len(sec) == 6
    assert all(sources[name] == {"status": "disabled_blocked", "reason": "SEC iletişim e-postası gerektiriyor; henüz tanımlanmadı", "no_retry": True} for name in sec)
    assert not any("@" in entry["reason"] for entry in sources.values()), "no e-mail address anywhere"
    assert set(sources) <= {row["name"] for row in source_catalog.read_rows()}
