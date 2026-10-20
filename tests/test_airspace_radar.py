"""Tests for Airspace & Conflict Zones Radar (EASA CZIB / NOTAM / Conflict Zones)."""

import xml.etree.ElementTree as ET
from pathlib import Path
from api import airspace_radar
from api import _engine

SAMPLE_CZIB_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Conflict Zone Information Bulletins (CZIBs)</title>
    <link>https://www.easa.europa.eu/en/domains/air-operations/czibs</link>
    <description>Active EASA conflict zone advisories</description>
    <item>
      <title>Airspace of Iran</title>
      <link>https://www.easa.europa.eu/en/domains/air-operations/czibs/czib-2024-01-r4</link>
      <pubDate>Mon, 14 Oct 2024 10:00:00 +0200</pubDate>
    </item>
    <item>
      <title>Airspace of Lebanon</title>
      <link>https://www.easa.europa.eu/en/domains/air-operations/czibs/czib-2024-02-r2</link>
      <pubDate>Tue, 15 Oct 2024 11:00:00 +0200</pubDate>
    </item>
    <item>
      <title>Airspace of Unknown Region</title>
      <link>https://www.easa.europa.eu/en/domains/air-operations/czibs/czib-2024-99</link>
      <pubDate>Wed, 16 Oct 2024 12:00:00 +0200</pubDate>
    </item>
  </channel>
</rss>
"""


def test_parse_czib_feed_valid_xml():
    items = airspace_radar.parse_czib_feed(SAMPLE_CZIB_XML)
    assert len(items) == 3
    assert items[0]["title"] == "Airspace of Iran"
    assert "czib-2024-01-r4" in items[0]["link"]
    assert items[1]["title"] == "Airspace of Lebanon"


def test_parse_czib_feed_empty_or_malformed():
    assert airspace_radar.parse_czib_feed("") == []
    assert airspace_radar.parse_czib_feed(None) == []
    assert airspace_radar.parse_czib_feed("<rss><invalid") == []


def test_match_known_region():
    key_iran, meta_iran = airspace_radar.match_known_region("Airspace of Iran")
    assert key_iran == "iran"
    assert meta_iran["fir"] == "OIIX (Tehran)"
    assert meta_iran["risk_level"] == "DO_NOT_OPERATE"

    key_lebanon, meta_lebanon = airspace_radar.match_known_region("Conflict Zone in Lebanon")
    assert key_lebanon == "lebanon"
    assert meta_lebanon["fir"] == "OLBB (Beirut)"

    key_none, meta_none = airspace_radar.match_known_region("Airspace of Iceland")
    assert key_none is None
    assert meta_none is None


def test_extract_bulletin_code():
    assert airspace_radar.extract_bulletin_code("https://www.easa.europa.eu/en/czibs/czib-2024-01-r4") == "CZIB-2024-01-R4"
    assert airspace_radar.extract_bulletin_code("https://example.com/2024-02-r1") == "2024-02-R1"
    assert airspace_radar.extract_bulletin_code("") == ""


def test_build_zone_record():
    record = airspace_radar.build_zone_record({
        "title": "Airspace of Iran",
        "link": "https://www.easa.europa.eu/en/domains/air-operations/czibs/czib-2024-01-r4",
        "pub_date": "Mon, 14 Oct 2024 10:00:00 +0200",
    })
    assert record["country"] == "İran"
    assert "Tehran" in record["fir"]
    assert record["risk_level"] == "DO_NOT_OPERATE"
    assert record["bulletin_code"] == "CZIB-2024-01-R4"
    assert "İran" in record["restriction_tr"] or "Tehran" in record["restriction_tr"]
    assert record["id"] == "iran"
    assert record["lat"] > 0
    assert record["lon"] > 0
    assert record["svg_x"] > 0
    assert record["svg_y"] > 0


def test_geo_to_svg():
    x, y = airspace_radar.geo_to_svg(0.0, 0.0)
    assert x == 500.0
    assert y == 250.0
    x_north, y_north = airspace_radar.geo_to_svg(90.0, 0.0)
    assert y_north == 0.0


def test_global_flight_traffic():
    traffic = airspace_radar.get_global_flight_traffic()
    assert traffic["status"] == "ok"
    assert traffic["daily_commercial_flights"] > 80000
    assert traffic["active_airborne_now"] > 5000
    assert "daily_commercial_flights_str" in traffic
    assert "active_airborne_now_str" in traffic
    assert len(traffic["regions"]) >= 4
    region_ids = [r["id"] for r in traffic["regions"]]
    assert "eurocontrol" in region_ids
    assert "faa" in region_ids


def test_fallback_zones():
    fallbacks = airspace_radar.get_fallback_zones()
    assert len(fallbacks) >= 5
    countries = [z["country"] for z in fallbacks]
    assert "İran" in countries
    assert "Ukrayna" in countries
    assert "Lübnan" in countries
    for z in fallbacks:
        assert "svg_x" in z and "svg_y" in z
        assert "id" in z


def test_load_radar_with_xml():
    radar = airspace_radar.load_radar(xml_text=SAMPLE_CZIB_XML)
    assert radar["status"] == "ok"
    assert radar["total_active_zones"] == 3
    assert radar["do_not_operate_count"] >= 2
    assert len(radar["zones"]) == 3
    # Check that DO_NOT_OPERATE zones come first
    first_level = radar["zones"][0]["risk_level"]
    assert first_level == "DO_NOT_OPERATE"
    assert "global_traffic" in radar
    assert radar["global_traffic"]["daily_commercial_flights"] > 80000


def test_load_radar_offline_fallback():
    # Passing empty string forces fallback
    radar = airspace_radar.load_radar(xml_text="")
    assert radar["status"] == "ok"
    assert radar["total_active_zones"] >= 5
    assert radar["do_not_operate_count"] >= 3
    assert "global_traffic" in radar
    assert radar["global_traffic"]["daily_commercial_flights"] > 80000


def test_ui_contract_airspace_elements():
    index_html = (Path(__file__).resolve().parents[1] / "public" / "index.html").read_text(encoding="utf-8")
    assert 'data-page="airspace"' in index_html
    assert 'id="airspace-alert-banner"' in index_html
    assert 'id="airspace-banner-btn"' in index_html
    assert 'id="nav-airspace-count"' in index_html
    assert 'renderAirspaceRadar' in index_html
    assert 'data-airspace-filter' in index_html
    assert 'airspace-map-card' in index_html
    assert 'airspace-map-svg' in index_html
    assert 'traffic-panel' in index_html
    assert 'data-map-zone' in index_html


def test_airspace_radar_browser_interaction():
    import json
    import pytest
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as engine:
        try:
            browser = engine.chromium.launch(channel="msedge", headless=True)
        except playwright.Error:
            pytest.skip("MS Edge not found")
            return
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        
        radar_data = airspace_radar.load_radar(xml_text="")
        mock_payload = {
            "date": "2026-10-20",
            "date_str": "2026-10-20",
            "stories": [],
            "status": "ok",
            "airspace_radar": radar_data,
            "market": {},
        }
        
        page.route("**/api/briefing*", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(mock_payload),
        ))
        
        index_url = "file:///" + str((Path(__file__).resolve().parents[1] / "public" / "index.html").as_posix())
        page.goto(index_url)
        page.wait_for_selector(".page-nav")
        
        # Navigate to airspace page
        page.click('[data-page="airspace"]')
        page.wait_for_selector(".airspace-map-card")
        
        # Verify traffic panel
        assert page.is_visible(".traffic-panel")
        assert "Bugünkü Ticari Uçuş" in page.text_content(".traffic-panel")
        
        # Verify map
        assert page.is_visible(".airspace-map-svg")
        markers = page.query_selector_all(".map-zone-group")
        assert len(markers) >= 5
        
        # Click on a map marker
        iran_marker = page.query_selector('[data-map-zone="iran"]')
        if iran_marker:
            iran_marker.click(force=True)
            page.wait_for_selector(".airspace-map-tooltip.active")
            assert "İran" in page.text_content("#tip-title")
        
        assert errors == []
        browser.close()
