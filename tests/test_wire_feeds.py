import json
import re

import pytest

from api import entities, feed_discovery, feed_sources, market_data, source_catalog

ROWS = {row["name"]: row for row in source_catalog.read_rows()}
PRN_ROWS = ("PR Newswire Travel Sector", "PR Newswire Heavy Industry Sector")
KAP_ROWS = ("KAP THYAO Disclosures", "KAP PGSUS Disclosures")
WIRE_ROWS = PRN_ROWS + ("GlobeNewswire Transportation Feed", "Business Wire Feeds")
INDEX = entities.EntityIndex.from_csv()

RSS_PAGE = """<button onclick="javascript:window.location.href='\\/rss\\/travel\\u002Dlatest\\u002Dnews\\/travel\\u002Dlatest\\u002Dnews\\u002Dlist.rss'"></button>"""


def test_the_wire_rows_exist_with_one_row_each_although_they_share_a_domain():
    keys = [source_catalog.row_key(ROWS[name]) for name in PRN_ROWS]
    assert len(set(keys)) == 2 and all(key.startswith("wire/prnewswire/") for key in keys)


@pytest.mark.parametrize("name", WIRE_ROWS)
def test_wire_rows_are_official_feed_only_sources_with_a_risk_flag_and_the_aviation_filter(name):
    row = ROWS[name]
    assert row["mode"] == "feed_only" and row["official"] == "true"
    assert row["source_type"] in {"airline_ir", "oem"}
    assert row["commercial_use_risk"] == "high"
    assert json.loads(row["notes"])["aviation_filter"] is True


def test_the_wire_risk_does_not_deactivate_a_source_that_opens():
    for name in WIRE_ROWS:
        row = ROWS[name]
        assert (row["status"] == "active") == (row["active"] == "1")
    assert {ROWS[name]["status"] for name in PRN_ROWS} <= {"active", "no_extractable_feed", "disabled_blocked"}


@pytest.mark.parametrize("name", KAP_ROWS)
def test_kap_is_recorded_as_having_no_public_feed_and_is_turkish(name):
    row = ROWS[name]
    assert row["status"] == "no_public_feed" and row["active"] == "0" and row["language"] == "tr"
    assert row["reason"]


def test_the_feed_paths_are_read_from_the_services_own_rss_page_not_written_by_hand():
    found = {match.replace("\\/", "/").replace("\\u002D", "-") for match in re.findall(r"window\.location\.href='([^']*\.rss)'", RSS_PAGE)}
    assert found == {"/rss/travel-latest-news/travel-latest-news-list.rss"}


def test_a_feed_address_as_start_url_is_accepted_by_the_discovery(monkeypatch):
    feed = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
    <item><title>Airline X prices notes</title><link>https://x.example/1</link><pubDate>Fri, 16 Oct 2026 08:00:00 GMT</pubDate></item></channel></rss>"""

    def fetch(url, headers, timeout):
        if url.endswith("robots.txt"):
            return feed_discovery.Response(404, b"", {}, url, 0.01, "HTTPError 404")
        return feed_discovery.Response(200, feed, {}, url, 0.01, "")

    fetcher = feed_discovery.PoliteFetcher(fetch=fetch, sleep=lambda seconds: None)
    now = feed_discovery.parse_datetime("Sat, 17 Oct 2026 08:00:00 GMT")
    result = feed_discovery.discover(fetcher, ["https://www.prnewswire.com/rss/travel-latest-news/travel-latest-news-list.rss"], now=now, allowed_methods=feed_discovery.FEED_ONLY_METHODS)
    assert result.status == feed_discovery.STATUS_FOUND and result.method == "rss"


def article(title, description=""):
    item = {"title": title, "description": description}
    entities.annotate_articles([item], INDEX)
    return item


def test_the_aviation_filter_drops_unrelated_wire_releases_and_keeps_airline_ones():
    assert not feed_sources.passes_aviation_filter(article("Acme Corp. launches new project-management software"), INDEX)
    assert feed_sources.passes_aviation_filter(article("Delta Air Lines reports September quarter financial results"), INDEX)


@pytest.mark.parametrize("title, expected", [
    ("Delta Air Lines Reports September Quarter 2026 Financial Results", "airline_financials"),
    ("United Airlines raises full-year earnings guidance", "airline_financials"),
    ("Alaska Air Group declares quarterly dividend", "airline_financials"),
    ("Boeing announces $2 billion share repurchase program", "capital_markets"),
])
def test_investor_announcements_use_existing_types_without_a_new_taxonomy_type(title, expected):
    result = market_data.classify_event_type(title, "")
    assert result and result["event_type"] == expected
    assert "investor_disclosure" not in market_data.load_taxonomy_config()["event_types"]


def test_a_debt_offering_has_no_type_yet_which_is_why_a_new_type_is_only_proposed():
    assert market_data.classify_event_type("JetBlue prices $500 million senior notes offering", "") is None
