"""Regression coverage for observed data provenance and honest panel availability."""

import copy
import sqlite3
from datetime import date, datetime, timezone

from api import _engine, briefing_store, fleet_watch, market_data, source_health

NOW = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)


def test_futures_write_does_not_relabel_or_modify_spot(tmp_path):
    database = tmp_path / "market.sqlite3"
    spot = [(date(2026, 10, 29), 78.5)]
    market_data.upsert_observations(database, {"brent_spot": spot}, provider_by_series={"brent_spot": "fred"})
    market_data.upsert_observations(database, {"brent_futures": [(date(2026, 10, 30), 80.0)]})
    assert market_data.load_observations(database, "brent_spot") == spot
    panel, _ = market_data.build_market_panel(database)
    stored_spot = next(item for item in panel["items"] if item["series_id"] == "brent_spot")
    assert stored_spot["source"] == "FRED (EIA)"


def test_contaminated_spot_cache_requires_observations_before_repair(tmp_path):
    database = tmp_path / "market.sqlite3"
    market_data.upsert_observations(database, {"brent_spot": [(date(2026, 10, 31), 999.0)]}, provider_by_series={"brent_spot": "ice"})
    market_data.upsert_observations(database, {"brent_futures": [(date(2026, 10, 31), 80.0)]})
    assert market_data.load_observations(database, "brent_spot") == []
    market_data.upsert_observations(database, {"brent_spot": []}, provider_by_series={"brent_spot": "fred"})
    assert market_data.load_observations(database, "brent_spot") == []
    verified = [(date(2026, 10, 29), 78.5)]
    market_data.upsert_observations(database, {"brent_spot": verified}, provider_by_series={"brent_spot": "fred"})
    assert market_data.load_observations(database, "brent_spot") == verified
    assert market_data.load_observations(database, "brent_futures") == [(date(2026, 10, 31), 80.0)]
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT count(*) FROM market_observations WHERE value = 999").fetchone()[0] == 0


def test_legacy_snapshot_never_republishes_futures_as_spot_or_iata_cache(monkeypatch):
    monkeypatch.setattr(market_data, "utc_now", lambda: NOW)
    stored = {"status": "ok", "items": [
        {"series_id": "brent_spot", "source": "ICE Futures", "value": 80, "as_of": "2026-10-30"},
        {"series_id": "jet_fuel_brent_crack_spread", "source": "IATA / Platts", "value": 65.47, "as_of": "2026-10-16"},
        {"series_id": "brent_futures", "source": "ICE Futures", "value": 80, "as_of": "2026-10-30"},
    ]}
    before = copy.deepcopy(stored)
    visible = market_data.apply_display_settings(stored)
    assert [item["series_id"] for item in visible["items"]] == ["brent_futures"]
    assert len(visible["quality_warnings"]) == 2
    assert stored == before


def test_weekly_observations_do_not_claim_a_daily_zero_and_stale_is_explicit(monkeypatch):
    monkeypatch.setattr(market_data, "utc_now", lambda: NOW)
    stored = {"status": "ok", "items": [{"series_id": "example", "source": "Approved weekly series", "frequency": "weekly",
        "value": 5, "as_of": "2026-10-16", "changes": {"daily_pct": 0}}]}
    item = market_data.apply_display_settings(stored)["items"][0]
    assert item["changes"]["daily_pct"] is None
    assert item["is_stale"] is True
    assert item["age_days"] == 16
    assert stored["items"][0]["changes"]["daily_pct"] == 0


def test_ecb_weekend_keeps_friday_observation_date(monkeypatch):
    monkeypatch.setattr(market_data, "utc_now", lambda: NOW)
    monkeypatch.setattr(market_data, "display_fx", lambda: True)
    market = {"items": [{"series_id": "fx_usd_eur", "source": "European Central Bank", "frequency": "business_daily", "as_of": "2026-10-30", "value": 0.9}]}
    item = market_data.apply_display_settings(market)["items"][0]
    assert item["as_of"] == "2026-10-30"
    assert item["carried_forward"] is True
    assert item["is_stale"] is False


def test_fleet_pipeline_runs_never_advance_verification_date():
    fleet = fleet_watch.load_fleet_watch(now=NOW)
    assert fleet["status"] == "stale"
    assert fleet["verified_age_days"] == 14
    assert fleet["last_verified_at"] == "2026-10-18T10:00:00+00:00"
    assert fleet["data_type"] == "manual_reference"


def test_source_health_separates_policy_exclusions_from_approved_feed_errors():
    rows = [{"name": "Good", "active": "1", "region": "Europe"},
            {"name": "Missing key", "active": "1", "region": "Global"},
            {"name": "Paid", "active": "0", "region": "North America"}]
    report = source_health.present_source_health({"sources": {
        "Good": {"status": "active"}, "Missing key": {"status": "not_configured"}, "Paid": {"status": "excluded_policy"}}}, rows=rows)
    assert report["reading_ok"] == 1
    assert report["configured_active"] == 2
    assert [issue["name"] for issue in report["issues"]] == ["Missing key"]
    assert report["status_counts"]["excluded_policy"] == 1
    assert "Africa" in report["coverage_gaps"]
    assert rows[2]["active"] == "0"


def test_no_source_report_is_unavailable_not_47_failed_feeds():
    report = source_health.present_source_health({}, rows=[{"name": "Approved", "active": "1", "region": "Europe"}])
    assert report["status"] == "unavailable"
    assert report["issues"] == []


def test_api_sanitizes_old_panels_without_regenerating_or_mutating_archive(monkeypatch):
    snapshot = {"date": "2026-11-01", "status": "ok", "stories": [], "market": {},
                "fleet_watch": {"last_verified_at": "2026-10-18T10:00:00+00:00", "programs": []},
                "airspace_radar": {"global_traffic": {"is_estimate": True, "daily_commercial_flights": 111200}, "zones": []}}
    monkeypatch.setattr(_engine.story_lifecycle, "utc_now", lambda: NOW)
    def reader(path):
        return copy.deepcopy(snapshot) if path == briefing_store.latest_path() else {}
    served = _engine.get_ready_briefing(reader=reader)
    assert served["airspace_radar"]["global_traffic"]["daily_commercial_flights"] is None
    assert served["fleet_watch"]["is_stale"] is True
    assert snapshot["airspace_radar"]["global_traffic"]["daily_commercial_flights"] == 111200
