import json
import sqlite3
from pathlib import Path

from api import _engine
from api import source_registry
from api.briefing import handler as briefing_handler
from api.refresh import handler as refresh_handler
from scripts.dev_server import resolve_public_file


def test_vercel_handlers_import():
    assert briefing_handler is not None
    assert refresh_handler is not None


def test_invalid_mode_is_rejected():
    try:
        _engine.validate_mode("unknown")
    except ValueError:
        return
    raise AssertionError("invalid briefing mode was accepted")


def test_public_file_resolution_blocks_traversal():
    assert resolve_public_file("../api/_engine.py") is None
    assert resolve_public_file("manifest.json").is_file()


def test_fallback_contains_only_source_material():
    result = _engine.fallback_briefing([{
        "title": "Source title",
        "description": "Source description",
        "source": "Source",
        "link": "https://example.com/story",
        "category_hint": "Route news",
    }])

    assert result["status"] == "degraded"
    assert result["stories"][0]["headline"] == "Source title"
    assert result["stories"][0]["original_source"]["url"] == "https://example.com/story"


def test_story_ids_are_stable_across_briefing_modes():
    source = {
        "title": "Connectivity update",
        "source_name": "Aviation Source",
        "url": "https://example.com/connectivity",
    }
    briefing = {
        "stories": [{
            "headline": "Connectivity update",
            "section": "Route news",
            "original_source": source,
        }]
    }

    daily = _engine.normalize_generated_briefing(briefing, "daily")
    hourly = _engine.normalize_generated_briefing(briefing, "hourly")

    assert daily["stories"][0]["id"] == hourly["stories"][0]["id"]


def test_generic_sources_are_filtered_to_airline_topics():
    assert _engine.is_airline_relevant("Airline adds a new route to Istanbul")
    assert not _engine.is_airline_relevant("Technology company launches a new phone")
    assert _engine.is_airline_relevant(
        "Quarterly results announced",
        source={"official": True, "source_type": "airline_ir"},
    )
    assert not _engine.is_airline_relevant(
        "What to eat in Çanakkale",
        source={"official": True, "source_type": "official_social"},
    )


def test_atom_entries_are_supported():
    payload = b'''<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Airline fleet update</title>
        <link href="https://example.com/fleet" />
        <summary>New aircraft deliveries.</summary>
        <updated>2026-10-14T12:00:00Z</updated>
      </entry>
    </feed>'''

    entries = _engine.parse_feed_entries(payload)
    title, link, description, published = _engine.entry_values(entries[0])
    assert title == "Airline fleet update"
    assert link == "https://example.com/fleet"
    assert description == "New aircraft deliveries."
    assert published.endswith("Z")


def test_verified_official_airline_feeds_are_registered():
    sources = {source["name"]: source for source in _engine.get_rss_sources()}
    assert sources["Lufthansa Group Newsroom"]["source_type"] == "airline_newsroom"
    assert sources["Delta News Hub"]["airline_code"] == "DL"
    assert sources["Emirates Newsroom"]["official"] is True


def test_official_press_cards_are_extracted_without_navigation_links():
    payload = b'''<nav><a href="/menu">Press Room</a></nav>
    <a class="press__link" href="/release" title="Airline route update">
      <h3>Airline route update</h3><p>01 October 2026 - New route announced.</p>
    </a>'''
    entries = _engine.extract_html_entries(payload, {
        "url": "https://example.com/en/press-room",
        "html_link_class": "press__link",
    })
    assert len(entries) == 1
    assert entries[0]["link"] == "https://example.com/release"
    assert entries[0]["pub_date"] == "01 October 2026"


def test_html_source_keeps_article_title_and_source_metadata_separate():
    payload = b'''<a href="/press-release/2026/item">14 Oct - Singapore Airlines expands its network</a>'''
    source = {
        "name": "Singapore Airlines Newsroom",
        "url": "https://example.com/corporate/newsroom/press-release/",
        "html_href_contains": "/press-release/",
    }
    entries = _engine.extract_html_entries(payload, source)
    assert entries[0]["title"] == "14 Oct - Singapore Airlines expands its network"


def test_major_airline_source_registry_is_present():
    sources = {source["name"]: source for source in _engine.get_rss_sources()}
    expected = {
        "American Airlines Newsroom": "AA",
        "United Airlines Newsroom": "UA",
        "Southwest Newsroom": "WN",
        "Air France Press Releases": "AF",
        "KLM Newsroom": "KL",
        "Air Canada News Releases": "AC",
        "Ryanair Newsroom": "FR",
        "easyJet Media Centre": "U2",
        "Qantas Newsroom": "QF",
        "Singapore Airlines Newsroom": "SQ",
        "ANA Group Press Releases": "NH",
        "Japan Airlines Press Releases": "JL",
        "Cathay Pacific Newsroom": "CX",
        "Air India Newsroom": "AI",
        "Etihad Airways News": "EY",
        "IndiGo Press Releases": "6E",
        "JetBlue Investor News": "B6",
        "Copa Holdings News Releases": "CM",
        "LATAM Investor Releases": "LA",
        "Alaska Airlines Newsroom": "AS",
    }
    assert {name: sources[name]["airline_code"] for name in expected} == expected


def test_configured_sources_keep_page_adapter_options(monkeypatch):
    monkeypatch.setenv("AIRLINE_BRIEFING_SOURCES_JSON", json.dumps([{
        "name": "Configured Airline IR",
        "url": "https://example.com/ir",
        "source_type": "airline_ir",
        "fetch_mode": "html",
        "html_link_class": "press__link",
        "date_required": True,
        "resolve_detail_dates": True,
    }]))
    records = _engine._configured_source_records()
    configured = next(record for record in records if record["name"] == "Configured Airline IR")
    assert configured["fetch_mode"] == "html"
    assert configured["date_required"] is True


def test_one_unavailable_source_does_not_block_other_feed_results(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'''<?xml version="1.0" encoding="utf-8"?>
            <rss><channel><item>
              <title>Airline adds a new route</title>
              <link>https://example.com/new-route</link>
              <description>Network expansion announced.</description>
            </item></channel></rss>'''

    sources = [
        {
            "name": "Unavailable source",
            "url": "https://example.com/unavailable",
            "category_hint": "Route news",
            "source_type": "trade_media",
        },
        {
            "name": "Available source",
            "url": "https://example.com/feed",
            "category_hint": "Route news",
            "source_type": "trade_media",
        },
    ]

    def fake_urlopen(request, **_kwargs):
        if request.full_url.endswith("unavailable"):
            raise OSError("source unavailable")
        return FakeResponse()

    monkeypatch.setattr(_engine, "get_rss_sources", lambda _max_hours: sources)
    monkeypatch.setattr(_engine.urllib.request, "urlopen", fake_urlopen)

    articles = _engine.fetch_rss_items()

    assert [article["source"] for article in articles] == ["Available source"]


def test_public_refresh_uses_cached_briefing_endpoint_without_html_errors():
    project_dir = Path(__file__).resolve().parents[1]
    for relative_path in ("index.html", "public/index.html", "static/index.html"):
        page = (project_dir / relative_path).read_text(encoding="utf-8")
        assert "/api/refresh?mode=" not in page
        assert "const cacheBuster = requestLatest" in page
        assert "Invalid API response" in page


def test_source_registry_migrates_current_sources_with_configured_tier_weights(tmp_path):
    database = tmp_path / "source_registry.sqlite3"
    source_registry.migrate_sources(_engine.get_builtin_source_records(), database)

    with sqlite3.connect(database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        lufthansa = connection.execute(
            "SELECT tier, reliability_weight, license_status FROM sources WHERE name = 'Lufthansa Group Newsroom'"
        ).fetchone()
        flightglobal = connection.execute(
            "SELECT tier, reliability_weight FROM sources WHERE name = 'FlightGlobal'"
        ).fetchone()
        source_stats_exists = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'source_stats'"
        ).fetchone()

    assert count == 36
    assert lufthansa == (1, 1.0, "public")
    assert flightglobal == (2, 0.8)
    assert source_stats_exists is not None


def test_paid_feed_keeps_body_out_of_article_processing(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'''<rss><channel><item>
                <title>Airline financial result</title>
                <link>https://example.com/result</link>
                <description>Licensed body text must never be kept.</description>
            </item></channel></rss>'''

    monkeypatch.setattr(_engine.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    articles, error = _engine._fetch_source_articles(
        {
            "name": "Licensed source",
            "url": "https://example.com/feed",
            "category_hint": "Other areas",
            "source_type": "mainstream",
            "license_status": "paid",
        },
        _engine.utc_now() - _engine.timedelta(days=1),
        {},
    )

    assert error == ""
    assert articles[0]["description"] == ""
    assert articles[0]["license_status"] == "paid"


def test_source_statistics_tracks_first_reporter_and_weekly_gaps(tmp_path):
    database = tmp_path / "source_registry.sqlite3"
    source_registry.migrate_sources([
        {"name": "Source A", "url": "https://example.com/a", "category_hint": "Other areas"},
        {"name": "Source B", "url": "https://example.com/b", "category_hint": "Other areas"},
    ], database)
    with sqlite3.connect(database) as connection:
        source_ids = dict(connection.execute("SELECT name, id FROM sources"))

    articles = [
        {"title": "Airline opens new Istanbul route", "link": "https://example.com/a/route", "timestamp": 10, "source_id": source_ids["Source A"]},
        {"title": "Airline opens new Istanbul route", "link": "https://example.com/b/route", "timestamp": 20, "source_id": source_ids["Source B"]},
    ]
    briefing = {"stories": [{"original_source": {"url": "https://example.com/a/route"}}]}

    assert source_registry.record_source_statistics(articles, briefing, database, report_date="2026-10-16")
    report = source_registry.weekly_source_report(database, end_date=__import__("datetime").date(2026, 10, 16))
    fastest = {source["name"]: source for source in report["fastest_sources"]}

    assert fastest["Source A"]["first_to_report_count"] == 1
    assert fastest["Source A"]["clusters_included_in_brief"] == 1
    assert {"region": "Africa", "tier": 1} in report["coverage_gaps"]


def test_source_candidates_are_never_enabled_by_default():
    project_dir = Path(__file__).resolve().parents[1]
    candidates = json.loads((project_dir / "config" / "source_candidates.json").read_text(encoding="utf-8"))["candidates"]

    assert candidates
    assert all(candidate["active"] is False for candidate in candidates)
