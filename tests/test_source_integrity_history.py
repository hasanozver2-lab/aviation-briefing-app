import copy
import json
import io
import urllib.error
from email.message import Message
from datetime import datetime, timedelta, timezone

import pytest

from api import benchmark_search, clustering, source_catalog, story_lifecycle


NOW = datetime(2026, 10, 19, 5, tzinfo=timezone.utc)
BOEING_URL = "https://www.boeing.com/commercial/market/commercial-market-outlook"


def test_publisher_name_cannot_impersonate_a_domain():
    assert benchmark_search.resolve_publisher_meta("https://example.com/invented", "Reuters") is None
    assert benchmark_search.approved_publisher("https://example.com/invented") is None


@pytest.mark.parametrize("url", [
    "https://www.reuters.com/business/airlines/test",
    "https://www.bloomberg.com/news/test",
    "https://www.ft.com/airlines/test",
    "https://www.oag.com/megahubs-airports-2025",
    "https://news.google.com/rss/articles/example",
    "https://boeing.com.evil.example/report",
    "https://boeing.com@127.0.0.1/report",
])
def test_unapproved_sources_and_redirect_links_cannot_be_publication_sources(url):
    assert benchmark_search.approved_publisher(url) is None


@pytest.mark.parametrize("override", [
    {"active": "0"}, {"status": "excluded_policy"}, {"mode": "feed_only"},
    {"license_status": "paid"}, {"notes": '{"license_required": true}'},
])
def test_csv_permissions_always_win_over_hardcoded_publisher_metadata(monkeypatch, override):
    rows = source_catalog.read_rows()
    row = next(copy.deepcopy(row) for row in rows if row["name"] == "Boeing News Releases")
    row.update(override)
    monkeypatch.setattr(source_catalog, "read_rows", lambda: [row])
    assert benchmark_search.approved_publisher(BOEING_URL) is None


def test_approved_publisher_reliability_comes_from_csv():
    publisher = benchmark_search.approved_publisher(BOEING_URL)
    assert publisher["name"] == "Boeing News Releases"
    assert publisher["reliability_weight"] == 1.0


def test_model_json_and_numbers_are_not_publisher_evidence():
    response = {"candidates": [{"content": {"parts": [{"text": json.dumps({
        "items": [{"title": "Airline orders 999 airplanes", "url": "https://example.com/fake",
                   "source_name": "Reuters", "published_at": "2026-10-19"}],
        "enrichments": [{"index": 0, "description": "Airline orders 999 airplanes for 123 billion dollars."}],
    })}]}}]}
    seeds = [{"description": "Publisher confirms an order."}]
    original = copy.deepcopy(seeds)
    assert benchmark_search.parse_search_response(response, NOW, NOW - timedelta(days=2)) == []
    assert benchmark_search.apply_search_enrichment(response, seeds) == 0
    assert seeds == original


def test_google_news_is_not_an_alternative_to_disabled_sources():
    def forbidden_opener(*args, **kwargs):
        pytest.fail("Google News must not be fetched")
    assert benchmark_search.fetch_google_news_query("airlines", NOW, NOW - timedelta(days=2), opener=forbidden_opener) == []


@pytest.mark.parametrize("html, expected", [
    ('<meta content="2026-10-17T14:30:00+03:00" property="article:published_time">', "2026-10-17T11:30:00+00:00"),
    ('<script type="application/ld+json">{"@type":"Article","datePublished":"2026-10-17"}</script>', "2026-10-17T00:00:00+00:00"),
    ('<h1>Market forecast 2026–2045</h1>', None),
    ('<meta property="article:published_time" content="2026-10-20">', None),
    ('<script type="application/ld+json">{"dateModified":"2026-10-18"}</script>', None),
])
def test_publication_dates_come_from_explicit_publisher_metadata(html, expected):
    result = benchmark_search.publication_date(html, NOW)
    assert (result.astimezone(timezone.utc).isoformat() if result else None) == expected


def test_old_article_timestamp_is_never_promoted_to_today():
    published = NOW - timedelta(days=2)
    article = benchmark_search._build_article("Airline announces Tokyo route", BOEING_URL, "Publisher summary",
                                             benchmark_search.approved_publisher(BOEING_URL), published, NOW)
    assert article["timestamp"] == published.timestamp()
    assert benchmark_search._parse_date_in_window("2026-10-19T04:30:00Z", NOW, NOW - timedelta(days=1)).hour == 4
    assert benchmark_search._parse_date_in_window("2026-10-17T04:30:00Z", NOW, NOW - timedelta(hours=48)) is None


def test_old_evergreen_page_metadata_is_not_the_release_date_of_a_new_report_edition():
    html = '<meta property="article:published_time" content="2023-12-08T14:17:25Z">'
    assert benchmark_search.publication_date(html, NOW, "Commercial Market Outlook 2026 - 2045") is None
    assert benchmark_search.publication_date(html, NOW, "Commercial Market Outlook 2024 - 2043") is not None


def test_undated_report_keeps_unknown_date_and_no_freshness_badges():
    article = benchmark_search._build_article("Boeing Commercial Market Outlook", BOEING_URL, "Publisher summary",
                                             benchmark_search.approved_publisher(BOEING_URL), None, NOW)
    assert article["timestamp"] == 0 and article["pub_date"] == ""
    story = {"first_seen_at": NOW.isoformat(), "publication_date_status": article["publication_date_status"],
             "is_strategic_report": True, "relevance_score": 80, "event_type": "airline_financials"}
    assert story_lifecycle.compute_badges(story, NOW) == []
    assert story_lifecycle.published_on_day(story, "2026-10-19", story_lifecycle.load_badges_config())


def route_article(title):
    return {"title": title, "event_type": "route_network_change", "timestamp": NOW.timestamp(),
            "entities": {"carriers": [{"entity_id": "carrier:000001", "name": "United"},
                                       {"entity_id": "carrier:000002", "name": "Air Canada"}]}}


def test_two_shared_airlines_and_event_type_do_not_merge_different_routes():
    opening = route_article("United and Air Canada open transborder routes to Boston")
    closing = route_article("United and Air Canada suspend winter service to Cancun")
    assert clustering.cluster_articles([opening, closing]) == [[0], [1]]


def test_same_route_report_still_merges_with_shared_event_evidence():
    title = "United and Air Canada announce six new routes to Boston"
    assert clustering.cluster_articles([route_article(title), route_article(title + " for summer 2027")]) == [[0, 1]]


def stored_story(identity, seen):
    return {"story_id": identity, "headline": "Airline adds Tokyo route", "relevance_score": 55,
            "sources": [{"name": "Official", "url": "https://example.com/" + identity}],
            "first_seen_at": seen, "last_updated_at": seen, "narrative_status": "done",
            "lead": "Saved narrative", "data_points": ["Publisher fact"]}


@pytest.mark.parametrize("force", [False, True])
def test_morning_scan_preserves_missing_stories_and_existing_narratives(force):
    seen = (NOW - timedelta(hours=4)).isoformat()
    saved = stored_story("same", seen)
    missing = {**stored_story("missing", seen), "headline": "Airport opens new terminal"}
    existing = {"stories": [saved, missing]}
    original = copy.deepcopy(existing)
    day = story_lifecycle.build_day(existing, None,
        {"daily": {"morning_deep_scan": True, "stories": [copy.deepcopy(saved)]}}, NOW, morning_reset=force)
    assert {story["story_id"] for story in day["stories"]} == {"same", "missing"}
    result = next(story for story in day["stories"] if story["story_id"] == "same")
    assert result["first_seen_at"] == seen
    assert result["last_updated_at"] == seen
    assert result["lead"] == "Saved narrative" and result["narrative_status"] == "done"
    assert existing == original


def test_morning_scan_keeps_history_when_story_is_seen_again_after_day_rollover():
    seen = (NOW - timedelta(days=1)).isoformat()
    previous = stored_story("same", seen)
    incoming = copy.deepcopy(previous)
    incoming.pop("first_seen_at")
    day = story_lifecycle.build_day(None, {"stories": [previous]},
        {"daily": {"morning_deep_scan": True, "stories": [incoming]}}, NOW)
    assert day["stories"][0]["first_seen_at"] == seen
    assert day["stories"][0]["narrative_status"] == "done"


def test_verified_date_correction_keeps_identity_and_narrative():
    seen = (NOW - timedelta(hours=2)).isoformat()
    target = stored_story("same", seen)
    target["published_at_iso"] = NOW.isoformat()
    incoming = {**copy.deepcopy(target), "published_at_iso": (NOW - timedelta(days=2)).isoformat(),
                "publication_date_status": "verified"}
    story_lifecycle._apply_incoming(target, incoming, NOW.isoformat(), story_lifecycle.load_badges_config())
    assert target["published_at_iso"] == incoming["published_at_iso"]
    assert target["first_seen_at"] == seen and target["narrative_status"] == "done"


def test_reseen_undated_report_clears_a_legacy_synthetic_publication_date():
    target = stored_story("report", (NOW - timedelta(days=1)).isoformat())
    target.update(is_strategic_report=True, published_at_iso=NOW.isoformat(), published_at="19 Oct 08:00")
    incoming = {**copy.deepcopy(target), "publication_date_status": "unknown", "published_at_iso": "", "published_at": ""}
    story_lifecycle._apply_incoming(target, incoming, NOW.isoformat(), story_lifecycle.load_badges_config())
    assert target["publication_date_status"] == "unknown" and target["published_at_iso"] == ""
    assert target["published_at"] == "" and target["narrative_status"] == "done"


def test_legacy_search_only_stories_are_hidden_without_deleting_archive_records():
    search = stored_story("search", NOW.isoformat())
    search["sources"][0]["url"] = "https://news.google.com/rss/articles/search"
    archive = {"stories": [search]}
    response = copy.deepcopy(archive)
    assert story_lifecycle.drop_excluded(response) == 1
    assert response["stories"] == []
    assert len(archive["stories"]) == 1


def test_real_publisher_source_can_corroborate_a_legacy_search_story():
    story = stored_story("real", NOW.isoformat())
    story["sources"][0]["url"] = "https://news.delta.com/released"
    story["sources"].append({"name": "Search", "url": "https://news.google.com/rss/articles/search"})
    assert not story_lifecycle.has_only_unverified_sources(story, story_lifecycle.load_relevance_config()["selection"])


def test_arbitrary_domain_cannot_rescue_a_search_only_story():
    story = stored_story("fake", NOW.isoformat())
    story["sources"].append({"name": "Search", "url": "https://news.google.com/rss/articles/search"})
    assert story_lifecycle.has_only_unverified_sources(story, story_lifecycle.load_relevance_config()["selection"])


class PageReply(io.BytesIO):
    def __init__(self, body, url):
        super().__init__(body.encode())
        self.url = url

    def geturl(self):
        return self.url


def test_disallowed_publication_path_is_not_requested():
    requested = []
    def opener(request, **kwargs):
        requested.append(request.full_url)
        return PageReply("User-agent: *\nDisallow: /commercial/", request.full_url)
    with pytest.raises(ValueError, match="robots"):
        benchmark_search._fetch_html_page(BOEING_URL, opener=opener)
    assert len(requested) == 1 and requested[0].endswith("/robots.txt")


@pytest.mark.parametrize("destination", ["https://127.0.0.1/private", "https://example.com/fake", "https://www.oag.com/report"])
def test_redirect_to_unapproved_publisher_is_never_followed(destination):
    requested = []
    def opener(request, **kwargs):
        requested.append(request.full_url)
        if request.full_url.endswith("robots.txt"):
            return PageReply("User-agent: *\nAllow: /", request.full_url)
        headers = Message()
        headers["Location"] = destination
        raise urllib.error.HTTPError(request.full_url, 301, "redirect", headers, None)
    with pytest.raises(ValueError, match="redirect"):
        benchmark_search._fetch_html_page(BOEING_URL, opener=opener)
    assert destination not in requested


def test_same_publisher_redirect_checks_robots_on_the_destination():
    destination = "https://www.boeing.com/commercial/market/new-report"
    requested = []
    def opener(request, **kwargs):
        requested.append(request.full_url)
        if request.full_url.endswith("robots.txt"):
            return PageReply("User-agent: *\nAllow: /", request.full_url)
        if request.full_url == destination:
            return PageReply("<h1>Verified report</h1>", destination)
        headers = Message()
        headers["Location"] = destination
        raise urllib.error.HTTPError(request.full_url, 301, "redirect", headers, None)
    assert benchmark_search._fetch_html_page(BOEING_URL, opener=opener) == "<h1>Verified report</h1>"
    assert requested.count("https://www.boeing.com/robots.txt") == 2
