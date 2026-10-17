"""Proof that generated artefacts (SQLite files, briefing caches) are not needed in git.

A fresh checkout has config/*.csv but no data/*.sqlite3 and no briefing_cache_*.json.
"""

import sqlite3
import time

import pytest

from api import _engine, source_catalog, briefing_store, market_data, source_registry


ARTICLES = [
    {
        "title": "THY signs 600-engine deal with CFM for A321neo", "description": "Turkish Airlines orders engines.",
        "source": "Example Wire", "link": "https://example.com/thy-cfm", "category_hint": "Route news",
        "source_type": "trade_media", "official": False, "timestamp": time.time(), "pub_date": "16 Oct 10:00",
    },
    {
        "title": "FAA orders inspections after Delta incident", "description": "", "source": "Example Wire",
        "link": "https://example.com/faa-delta", "category_hint": "Other areas", "source_type": "trade_media",
        "official": False, "timestamp": time.time(), "pub_date": "16 Oct 09:00",
    },
]


@pytest.fixture
def isolated_pipeline(tmp_path, monkeypatch):
    """Point every default path at an empty temp area, as on a fresh GitHub Actions runner."""
    registry_db = tmp_path / "source_registry.sqlite3"
    market_db = tmp_path / "pipeline.sqlite3"
    monkeypatch.setattr(source_registry, "DEFAULT_DATABASE_PATH", registry_db)
    monkeypatch.setattr(_engine, "CACHE_FILE_DAILY", tmp_path / "briefing_cache_daily.json")
    monkeypatch.setattr(_engine, "CACHE_FILE_HOURLY", tmp_path / "briefing_cache_hourly.json")
    monkeypatch.setattr(_engine, "GEMINI_API_KEY", "")
    monkeypatch.setattr(_engine, "fetch_rss_items", lambda max_hours=48, report=None: [dict(article) for article in ARTICLES])
    monkeypatch.setattr(market_data, "refresh_market_data", lambda *args, **kwargs: {"indicators": []})
    assert not registry_db.exists() and not market_db.exists()
    return registry_db, market_db


def test_pipeline_builds_registry_and_entities_from_the_seed_alone(isolated_pipeline):
    registry_db, market_db = isolated_pipeline

    collected = _engine.collect_run(market_database=market_db)

    with sqlite3.connect(registry_db) as connection:
        rows = source_catalog.read_rows()
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == len(rows)
        assert connection.execute("SELECT COUNT(*) FROM sources WHERE active = 1").fetchone()[0] == sum(1 for row in rows if row["status"] == "active")
    with sqlite3.connect(market_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM carriers").fetchone()[0] > 100
        assert connection.execute("SELECT COUNT(*) FROM airports").fetchone()[0] > 100
        assert connection.execute("SELECT COUNT(*) FROM groups").fetchone()[0] >= 10

    stories = {story["original_source"]["url"]: story for story in collected["stories"]}
    thy = stories["https://example.com/thy-cfm"]
    assert [carrier["slug"] for carrier in thy["entities"]["carriers"]] == ["turkish-airlines"]
    assert thy["entities"]["carriers"][0]["entity_id"].startswith("carrier:")
    assert (thy["region_section"], thy["secondary_tags"]) == ("Europe", ["Manufacturers & Supply Chain"])
    assert thy["event_type"] == "fleet_orders" and thy["narrative_status"] == "pending"
    assert collected["candidates"] == 2          # the FAA/Delta item is a candidate but scores below the selection threshold
    assert "https://example.com/faa-delta" not in stories


def test_pipeline_is_idempotent_when_the_databases_already_exist(isolated_pipeline):
    _, market_db = isolated_pipeline
    _engine.collect_run(market_database=market_db)
    _engine.collect_run(market_database=market_db)
    with sqlite3.connect(market_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM carriers WHERE slug = 'turkish-airlines'").fetchone()[0] == 1


@pytest.mark.parametrize("mode", ["daily", "hourly"])
def test_api_answers_without_any_local_cache_file(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(_engine, "CACHE_FILE_DAILY", tmp_path / "missing_daily.json")
    monkeypatch.setattr(_engine, "CACHE_FILE_HOURLY", tmp_path / "missing_hourly.json")
    monkeypatch.setattr(briefing_store, "read_json", lambda path: None)

    result = _engine.get_ready_briefing(mode)

    assert result["status"] == "unavailable" and result["stories"] == []
    assert result["mode"] == mode


def test_api_serves_the_blob_snapshot_when_no_cache_file_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(_engine, "CACHE_FILE_DAILY", tmp_path / "missing_daily.json")
    snapshot = {"mode": "daily", "status": "ok", "generated_at": "2026-10-16T08:00:00+00:00", "stories": [{"id": "s"}]}
    monkeypatch.setattr(briefing_store, "read_json", lambda path: snapshot if path.endswith("latest.json") else {})

    result = _engine.get_ready_briefing("daily")

    assert result["status"] == "ok" and result["stories"] == [{"id": "s"}]
