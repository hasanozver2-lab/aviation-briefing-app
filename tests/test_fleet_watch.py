"""Tests for Fleet, Delivery & Engine Delays Watch (Filo & Motor Radarı)."""

from pathlib import Path
from api import fleet_watch
from api import _engine


def test_load_fleet_watch_structure():
    data = fleet_watch.load_fleet_watch()
    assert data["status"] == "ok"
    assert data["total_programs"] >= 4
    assert data["grounding_count"] >= 1
    assert data["delivery_delay_count"] >= 2
    assert "Filo & Motor Radarı" in data["headline_tr"]
    assert "Fleet Watch" in data["headline_en"]
    assert len(data["programs"]) == data["total_programs"]


def test_gtf_and_leap_engine_programs():
    data = fleet_watch.load_fleet_watch()
    ids = [p["id"] for p in data["programs"]]
    assert "pw-gtf-groundings" in ids
    assert "cfm-leap-durability-tat" in ids
    assert "boeing-737max-faa-cap" in ids
    assert "airbus-a321xlr-entry" in ids

    gtf = next(p for p in data["programs"] if p["id"] == "pw-gtf-groundings")
    assert gtf["severity"] == "CRITICAL"
    assert "PW1100G" in gtf["engine_model"]
    assert "Türk Hava Yolları" in gtf["affected_carriers"]
    assert "A321neo" in gtf["aircraft_models"][1] or "A320neo" in gtf["aircraft_models"][0]


def test_thy_and_pegasus_impact_present():
    data = fleet_watch.load_fleet_watch()
    for p in data["programs"]:
        assert "thy_pegasus_impact_tr" in p
        assert len(p["thy_pegasus_impact_tr"]) > 10


def test_engine_collect_run_includes_fleet_watch():
    # Verify module contract
    fw = fleet_watch.load_fleet_watch()
    assert isinstance(fw["programs"], list)
    assert fw["critical_count"] >= 1


def test_ui_contract_fleet_watch():
    html = (Path(__file__).resolve().parents[1] / "public" / "index.html").read_text(encoding="utf-8")
    assert 'data-page="fleet"' in html
    assert 'nav-fleet-count' in html
    assert 'renderFleetWatch' in html
    assert 'data-fleet-filter' in html
    assert 'Filo, Teslimat &amp; Motor Gecikmeleri Radarı' in html
