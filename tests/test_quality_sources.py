from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

import pytest

from api import _engine, feed_discovery as fd, feed_sources, source_catalog

NOW = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
ICAO_URL = "https://www.icao.int/news"


def card(title, date, url="/news/example"):
    return (f'<div class="card-contents"><div class="card-type">News</div><div class="card-date">{date}</div>'
            f'<div class="card-title"><a href="{url}">{title}</a></div>'
            '<div class="more-arrow-wrap"><a href="/news/other">Read more</a></div></div>')


def test_icao_cards_keep_each_title_with_its_own_date():
    page = card("Civil aviation agreement", "15/10/26", "/news/first") + card("Air traffic safety update", "14/10/26", "/news/second")
    method, items = fd.classify_body(page.encode(), ICAO_URL)
    assert method == "html"
    assert [(item.title, item.published.day, item.link) for item in items] == [
        ("Civil aviation agreement", 15, "https://www.icao.int/news/first"),
        ("Air traffic safety update", 14, "https://www.icao.int/news/second")]


@pytest.mark.parametrize("date", ["", "31/02/26", "today"])
def test_bad_card_dates_are_not_borrowed_from_a_neighbour(date):
    page = card("Missing date", date, "/news/bad") + card("Correct dated notice", "15/10/26", "/news/good")
    _, items = fd.classify_body(page.encode(), ICAO_URL)
    assert [item.title for item in items] == ["Correct dated notice"]


def test_card_parser_is_scoped_to_the_publisher_and_rejects_external_links():
    page = card("Unrelated heading", "15/10/26")
    assert fd.classify_body(page.encode(), "https://unrelated.example/news")[1] == []
    assert fd.classify_body(card("External link", "15/10/26", "https://unrelated.example/news").encode(), ICAO_URL)[1] == []


def test_nested_card_text_and_void_tags_preserve_unicode():
    page = card("<span>İstanbul &amp; aviation</span><br/> update", "15/10/26")
    assert fd.classify_body(page.encode(), ICAO_URL)[1][0].title == "İstanbul & aviation update"


def setup_feed(monkeypatch, headlines):
    row = next(row for row in source_catalog.read_rows() if row["name"] == "BBC News Business")
    source = feed_sources.source_record(row)
    entries = "".join(
        f"<item><title>{escape(title)}</title><link>https://www.bbc.com/news/{number}</link>"
        f"<pubDate>{stamp.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate></item>"
        for number, (title, stamp) in enumerate(headlines))
    body = f"<rss><channel>{entries}</channel></rss>".encode()

    class Reader:
        timeout = 10

        def get(self, url, **kwargs):
            return fd.Response(status=200, body=body, final_url=row["feed_url"])

    monkeypatch.setattr(source_catalog, "read_rows", lambda: [row])
    monkeypatch.setattr(feed_sources, "load_discovered", lambda: {source["slug"]: {"feed_url": row["feed_url"], "method": "rss"}})
    monkeypatch.setattr(fd, "PoliteFetcher", Reader)
    monkeypatch.setattr(_engine, "utc_now", lambda: NOW)


def test_aviation_headline_after_first_25_business_items_is_not_lost(monkeypatch):
    headlines = [(f"Retail company earnings report {number}", NOW) for number in range(30)]
    headlines.append(("Airline launches new service to Tokyo", NOW - timedelta(hours=1)))
    setup_feed(monkeypatch, headlines)
    report = {}
    articles = _engine._read_catalog_feeds(NOW - timedelta(hours=48), report)
    assert [item["title"] for item in articles] == ["Airline launches new service to Tokyo"]
    assert report["BBC News Business"]["filtered_out"] == 30
    assert report["BBC News Business"]["articles"] == 1
    assert articles[0]["basis"] == "headline_only"


def test_general_feed_still_obeys_quota_after_filtering_and_rejects_future_dates(monkeypatch):
    headlines = [("Airline future notice", NOW + timedelta(days=1))]
    headlines += [(f"Airline service expansion {number}", NOW - timedelta(minutes=number)) for number in range(30)]
    setup_feed(monkeypatch, headlines)
    articles = _engine._read_catalog_feeds(NOW - timedelta(hours=48), {})
    assert len(articles) == feed_sources.MAX_ITEMS_PER_SOURCE
    assert all(item["timestamp"] <= NOW.timestamp() for item in articles)


def test_quality_feeds_are_registered_and_restricted_sources_remain_closed():
    rows = {row["name"]: row for row in source_catalog.read_rows()}
    discovered = feed_sources.load_discovered()
    for name in ("IATA Press Room", "ICAO Newsroom", "ACI World News", "The New York Times", "BBC News Business"):
        row = rows[name]
        assert row["active"] == "1"
        assert row["feed_url"] == discovered[source_catalog.source_slug(name)]["feed_url"]
    for name in ("Reuters Aviation", "Bloomberg Aviation"):
        assert rows[name]["active"] == "0"
