import json
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pytest

from api import _engine, alert_feeds, entities, feed_discovery as fd, feed_sources, narrative, source_catalog, source_probe
from scripts import run_pipeline

NOW = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(hours=48)
FEED_ONE = "https://www.google.com/alerts/feeds/00000000000000000001/11111111111111111111"
FEED_TWO = "https://www.google.com/alerts/feeds/00000000000000000002/22222222222222222222"
SECRET_FRAGMENTS = ("00000000000000000001", "11111111111111111111", "00000000000000000002", "22222222222222222222", "alerts/feeds")
INDEX = entities.EntityIndex.from_csv()


def redirect(target):
    return f"https://www.google.com/url?rct=j&amp;sa=t&amp;url={quote(target, safe='')}&amp;ct=ga&amp;cd=CAEYAA&amp;usg=AOvVaw0"


def entry(title, target, when, summary="Short snippet about the story."):
    return (f'<entry><title type="html">{title}</title><link href="{redirect(target)}"/><published>{when}</published>'
            f'<content type="html">{summary}</content></entry>')


def atom(*entries):
    return ('<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Google Alert</title>' + "".join(entries) + "</feed>").encode()


FEED_BODY = atom(
    entry("&lt;b&gt;Ryanair&lt;/b&gt; cancels 300 flights as strike bites", "https://www.reuters.com/business/aerospace-defense/ryanair-cancels-2026-10-16/", "2026-10-16T18:00:00Z"),
    entry("&lt;b&gt;Delta Air Lines&lt;/b&gt; orders more jets", "https://www.bloomberg.com/news/articles/2026-10-16/delta-orders", "2026-10-16T12:00:00Z"),
    entry("Local council approves new bakery", "https://www.wsj.com/articles/bakery", "2026-10-16T10:00:00Z", "Bread and pastry."),
    entry("&lt;b&gt;Lufthansa&lt;/b&gt; pilots vote on strike", "https://apnews.com/article/lufthansa-pilots", "2026-10-10T10:00:00Z"),
)


class FakeFeeds:
    def __init__(self, pages):
        self.pages, self.requested = pages, []

    def __call__(self, url, headers, timeout):
        self.requested.append(url)
        status, body = self.pages.get(url, (404, b""))
        return fd.Response(status, body, {}, url, 0.01, "" if status == 200 else f"HTTPError {status}")


def collect(raw, pages, **kwargs):
    transport = FakeFeeds(pages)
    fetcher = fd.PoliteFetcher(fetch=transport, sleep=lambda seconds: None)
    articles, report = alert_feeds.collect(raw, NOW, CUTOFF, entity_index_factory=lambda: INDEX, fetcher=fetcher, **kwargs)
    return articles, report, transport


# --- configuration ---------------------------------------------------------------------------------------------------------

def test_one_address_per_line_blank_lines_and_comments_are_skipped_and_bad_lines_are_only_counted():
    urls, ignored = alert_feeds.parse_feed_urls(f"{FEED_ONE}\n\n# note\nnot an address\n{FEED_TWO}\n{FEED_ONE}\n")
    assert urls == [FEED_ONE, FEED_TWO] and ignored == 1


@pytest.mark.parametrize("raw", ["", None, "   \n\n", "# only a comment"])
def test_a_missing_variable_is_reported_as_not_configured_never_skipped_silently(raw):
    articles, report = alert_feeds.collect(raw, NOW, CUTOFF)
    assert articles == [] and report["status"] == "not_configured" and report["error"]


def test_not_configured_reaches_status_json(monkeypatch):
    monkeypatch.setattr(source_catalog, "read_rows", lambda path=None: [{"name": alert_feeds.SOURCE_NAME, "status": "active", "reason": "x"}])
    _, report = alert_feeds.collect("", NOW, CUTOFF)
    health = run_pipeline.source_health({alert_feeds.SOURCE_NAME: report}, {}, NOW)
    assert health[alert_feeds.SOURCE_NAME]["status"] == "not_configured"
    assert run_pipeline.source_summary(health)["unresolved"] == 1


# --- redirect, publisher --------------------------------------------------------------------------------------------------

def test_the_publisher_address_comes_out_of_the_google_redirect():
    target = "https://www.reuters.com/business/ryanair?a=1&b=2"
    assert alert_feeds.target_url(redirect(target).replace("&amp;", "&")) == target
    assert alert_feeds.target_url("https://www.google.co.uk/url?q=" + quote(target, safe="")) == target
    assert alert_feeds.target_url("https://www.reuters.com/direct") == "https://www.reuters.com/direct"


@pytest.mark.parametrize("link", ["", "https://www.google.com/url?sa=t", "https://www.google.com/url?url=javascript:alert(1)", "ftp://x.example/a"])
def test_an_unusable_link_is_dropped(link):
    assert alert_feeds.target_url(link) == ""


@pytest.mark.parametrize("url, name", [
    ("https://www.reuters.com/a", "Reuters"), ("https://www.bloomberg.com/a", "Bloomberg"), ("https://www.wsj.com/a", "WSJ"),
    ("https://apnews.com/a", "AP"), ("https://www.ft.com/content/a", "FT"), ("https://example-news.com/a", "Example News"),
])
def test_the_publisher_name_comes_from_the_target_domain(url, name):
    assert alert_feeds.publisher_name(url) == name


# --- reading --------------------------------------------------------------------------------------------------------------

def test_items_become_headline_only_stories_inputs_with_the_publishers_link():
    articles, report, transport = collect(FEED_ONE, {FEED_ONE: (200, FEED_BODY)})
    by_source = {article["source"]: article for article in articles}
    assert set(by_source) == {"Reuters", "Bloomberg"}, "the bakery item fails the aviation filter, the Lufthansa item is older than the window"
    reuters = by_source["Reuters"]
    assert reuters["link"] == "https://www.reuters.com/business/aerospace-defense/ryanair-cancels-2026-10-16/"
    assert reuters["title"] == "Ryanair cancels 300 flights as strike bites"
    assert reuters["basis"] == "headline_only" and reuters["source_type"] == "wire_headline" and reuters["official"] is False and reuters["tier"] == 3
    assert len(reuters["description"]) <= feed_sources.FEED_ONLY_SUMMARY_CHARS
    assert report["status"] == "active" and report["articles"] == 2 and report["filtered_out"] == 1 and report["error"] == ""


def test_only_the_alert_feed_is_requested_never_a_publisher_page_or_robots_file():
    _, _, transport = collect(f"{FEED_ONE}\n{FEED_TWO}", {FEED_ONE: (200, FEED_BODY), FEED_TWO: (200, FEED_BODY)})
    assert transport.requested == [FEED_ONE, FEED_TWO]


def test_one_logical_source_stands_in_the_catalog_with_the_agreed_reason_and_risk():
    rows = {row["name"]: row for row in source_catalog.read_rows()}
    row = rows[alert_feeds.SOURCE_NAME]
    assert row["commercial_use_risk"] == "high" and row["source_type"] == "wire_headline" and row["mode"] == "feed_only"
    assert row["reason"] == "Google Alerts kişisel kullanım; yayıncı başlıkları ticari katmanda yeniden değerlendirilecek"
    assert sum(1 for name in rows if "Google Alerts" in name) == 1


def test_the_generic_catalog_reader_and_the_probe_leave_the_alert_source_alone():
    record = alert_feeds.catalog_record()
    probe_record, articles = source_probe.probe_source({row["name"]: row for row in source_catalog.read_rows()}[alert_feeds.SOURCE_NAME], record, {}, {}, NOW)
    assert articles == [] and probe_record["status"] == "active" and probe_record["requests"] == 0
    assert "alert_feeds.SOURCE_NAME}" in open(_engine.__file__, encoding="utf-8").read()


def test_narrative_rules_for_headline_only_apply_to_alert_articles():
    articles, _, _ = collect(FEED_ONE, {FEED_ONE: (200, FEED_BODY)})
    story = {"basis": narrative.BASIS_HEADLINE_ONLY, "headline": articles[0]["title"], "source_description": articles[0]["description"]}
    fields, removed = narrative.sanitize_headline_only({"lead": "Ryanair cancelled 999 flights.", "data_points": []}, f"{story['headline']} {story['source_description']}")
    assert removed and "999" not in json.dumps(fields)


# --- the addresses are secret -----------------------------------------------------------------------------------------------

def assert_no_secret(text):
    for fragment in SECRET_FRAGMENTS:
        assert fragment not in text, fragment


def test_failures_name_the_feed_by_position_and_never_contain_the_address():
    pages = {FEED_ONE: (404, b""), FEED_TWO: (200, b"<html>not a feed</html>")}
    articles, report, _ = collect(f"{FEED_ONE}\n{FEED_TWO}\nnot-an-address-" + "1" * 20, pages)
    assert articles == []
    assert "alert feed 1: HTTP 404" in report["error"] and "alert feed 2: not a valid feed" in report["error"] and "ignored" in report["error"]
    assert_no_secret(json.dumps(report))


def test_a_transport_exception_whose_text_holds_the_address_is_not_repeated():
    def broken(url, headers, timeout):
        raise OSError(f"cannot reach {url}")

    fetcher = fd.PoliteFetcher(fetch=broken, sleep=lambda seconds: None)
    articles, report = alert_feeds.collect(FEED_ONE, NOW, CUTOFF, fetcher=fetcher)
    assert report["error"] == "alert feed 1: OSError"
    assert_no_secret(json.dumps(report))


def test_the_status_payload_built_from_a_run_carries_no_address(monkeypatch):
    _, report, _ = collect(f"{FEED_ONE}\n{FEED_TWO}", {FEED_ONE: (200, FEED_BODY), FEED_TWO: (500, b"")})
    health = run_pipeline.source_health({alert_feeds.SOURCE_NAME: report}, {}, NOW)
    assert_no_secret(json.dumps(health, ensure_ascii=False))
    assert health[alert_feeds.SOURCE_NAME]["status"] == run_pipeline.STATUS_FETCH_ERROR, "a partly failing source is visible in status.json"


def test_the_workflow_passes_the_secret_and_nothing_prints_it():
    workflow = open(".github/workflows/briefing-pipeline.yml", encoding="utf-8").read()
    assert "ALERT_FEEDS: ${{ secrets.ALERT_FEEDS }}" in workflow
    source = open(alert_feeds.__file__, encoding="utf-8").read()
    assert "print(" not in source and "logging" not in source


def test_per_publisher_counts_for_the_local_report():
    articles, _, _ = collect(FEED_ONE, {FEED_ONE: (200, FEED_BODY)})
    assert alert_feeds.publisher_counts(articles) == {"Reuters": 1, "Bloomberg": 1}
