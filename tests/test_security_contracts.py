from api import _engine
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
