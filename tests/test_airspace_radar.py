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


def test_fallback_zones():
    fallbacks = airspace_radar.get_fallback_zones()
    assert len(fallbacks) >= 5
    countries = [z["country"] for z in fallbacks]
    assert "İran" in countries
    assert "Ukrayna" in countries
    assert "Lübnan" in countries


def test_load_radar_with_xml():
    radar = airspace_radar.load_radar(xml_text=SAMPLE_CZIB_XML)
    assert radar["status"] == "ok"
    assert radar["total_active_zones"] == 3
    assert radar["do_not_operate_count"] >= 2
    assert len(radar["zones"]) == 3
    # Check that DO_NOT_OPERATE zones come first
    first_level = radar["zones"][0]["risk_level"]
    assert first_level == "DO_NOT_OPERATE"


def test_load_radar_offline_fallback():
    # Passing empty string forces fallback
    radar = airspace_radar.load_radar(xml_text="")
    assert radar["status"] == "ok"
    assert radar["total_active_zones"] >= 5
    assert radar["do_not_operate_count"] >= 3


def test_ui_contract_airspace_elements():
    index_html = (Path(__file__).resolve().parents[1] / "public" / "index.html").read_text(encoding="utf-8")
    assert 'data-page="airspace"' in index_html
    assert 'id="airspace-alert-banner"' in index_html
    assert 'id="airspace-banner-btn"' in index_html
    assert 'id="nav-airspace-count"' in index_html
    assert 'renderAirspaceRadar' in index_html
    assert 'data-airspace-filter' in index_html
