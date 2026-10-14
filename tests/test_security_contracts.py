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
