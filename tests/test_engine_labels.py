import pytest

from api import _engine, entities


# --- model payload and published JSON -----------------------------------------

def test_description_limit_comes_from_config_and_defaults_to_800():
    assert _engine.load_description_limit() == 800
    article = {"title": "T", "source": "S", "link": "https://example.com/a", "description": "x" * 1000}
    assert len(_engine.build_compact_articles([article])[0]["description"]) == 800
    assert len(_engine.build_compact_articles([article], description_limit=200)[0]["description"]) == 200


def test_model_payload_carries_event_type_and_entity_codes():
    found = {
        "carriers": [{"iata": "TK", "name": "Turkish Airlines", "region": "Europe"}],
        "airports": [],
        "aircraft": [{"code": "A220", "family": "A220", "manufacturer": "Airbus"}],
    }
    article = {"title": "T", "source": "S", "link": "https://example.com/a", "description": "", "event_type": "fuel_energy", "entities": found}
    compact = _engine.build_compact_articles([article])[0]
    assert compact["event_type"] == "fuel_energy"
    assert compact["entities"] == {"groups": [], "carriers": ["TK"], "airports": [], "aircraft": ["A220"]}


def test_published_story_carries_deterministic_labels_from_the_source_article():
    found = {"carriers": [{"iata": "TK", "name": "Turkish Airlines", "region": "Europe"}], "airports": [], "aircraft": []}
    article = {"link": "https://example.com/a", "event_type": "fuel_energy", "entities": found, "region_section": "Europe"}
    briefing = {"stories": [{"headline": "H", "section": "Route news", "original_source": {"url": "https://example.com/a"}}]}
    story = _engine.normalize_generated_briefing(briefing, "daily", {_engine.canonicalize_url(article["link"]): article})["stories"][0]
    assert (story["event_type"], story["region_section"], story["entities"]) == ("fuel_energy", "Europe", found)


def test_published_story_carries_secondary_tags():
    article = {"link": "https://example.com/a", "region_section": "Europe", "secondary_tags": ["Manufacturers & Supply Chain"]}
    briefing = {"stories": [{"headline": "H", "section": "Route news", "original_source": {"url": "https://example.com/a"}}]}
    story = _engine.normalize_generated_briefing(briefing, "daily", {_engine.canonicalize_url(article["link"]): article})["stories"][0]
    assert story["secondary_tags"] == ["Manufacturers & Supply Chain"]


def test_fallback_story_without_labels_has_explicit_empty_defaults():
    story = _engine.fallback_briefing([{"title": "T", "link": "https://example.com/a", "source": "S"}])["stories"][0]
    assert story["event_type"] is None
    assert story["entities"] == entities.empty_entities()
    assert story["region_section"] == ""
    assert story["secondary_tags"] == []


def test_read_only_api_path_does_not_need_pipeline_config(tmp_path, monkeypatch):
    from api import blob_store
    monkeypatch.setattr(_engine, "PIPELINE_CONFIG_PATH", tmp_path / "missing.json")
    monkeypatch.setattr(_engine, "CACHE_FILE_DAILY", tmp_path / "missing_daily.json")
    monkeypatch.setattr(blob_store, "get_public_json", lambda path: None)
    assert _engine.get_ready_briefing("daily")["status"] == "unavailable"
    with pytest.raises(FileNotFoundError):
        _engine.build_compact_articles([{"title": "T", "source": "S", "link": "https://example.com/a", "description": "x"}])
