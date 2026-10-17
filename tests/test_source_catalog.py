import json

import pytest

from api import source_catalog

TYPES = source_catalog.load_source_types()
EXPANSION = json.loads(source_catalog.EXPANSION_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("url, key", [
    ("https://news.delta.com/rss.xml", "delta.com"),
    ("https://www.united.com/en/us/newsroom", "united.com"),
    ("https://www.ana.co.jp/group/en/pr/", "ana.co.jp"),
    ("https://press.jal.co.jp/en/", "jal.co.jp"),
    ("https://web.shgm.gov.tr/", "shgm.gov.tr"),
    ("https://www.kap.org.tr/en/", "kap.org.tr"),
    ("https://www.easa.europa.eu/en/newsroom", "www.easa.europa.eu"),
    ("https://www.gov.br/anac/en", "gov.br/anac"),
    ("https://www.gov.uk/government/organisations/air-accidents-investigation-branch", "gov.uk/government/organisations/air-accidents-investigation-branch"),
    ("https://www.qantasnewsroom.com.au/", "qantasnewsroom.com.au"),
])
def test_registrable_key(url, key):
    assert source_catalog.registrable_key(url) == key


def test_two_agencies_on_a_shared_host_are_two_publishers():
    assert source_catalog.registrable_key("https://www.gov.uk/government/organisations/a") != source_catalog.registrable_key("https://www.gov.uk/government/organisations/b")
    assert source_catalog.registrable_key("https://www.easa.europa.eu/") != source_catalog.registrable_key("https://ec.europa.eu/")


def test_the_catalog_has_no_two_rows_for_one_publisher():
    rows = source_catalog.read_rows()
    keys = [source_catalog.row_key(row) for row in rows]
    duplicates = {key for key in keys if keys.count(key) > 1}
    # existing rows that already shared a domain before the expansion (Yahoo Finance feeds) are the only allowed repeats
    assert duplicates <= {"yahoo.com"}, duplicates


def test_every_expansion_source_is_in_the_catalog_and_the_merge_is_idempotent():
    rows = source_catalog.read_rows()
    keys = {source_catalog.row_key(row) for row in rows}
    for entry in EXPANSION["sources"]:
        key = f"sec/{entry['cik']}" if entry.get("cik") else entry.get("catalog_key") or source_catalog.registrable_key(entry["urls"][0])
        assert key in keys, entry["name"]
    merged, report = source_catalog.merge_expansion(rows, EXPANSION)
    assert report["added"] == [] and merged == rows


def test_an_existing_domain_is_updated_not_duplicated():
    rows = [{"name": "Delta News Hub", "url": "https://news.delta.com/rss.xml", "feed_url": "x", "feed_type": "rss", "region": "North America", "tier": "1",
             "license_status": "public", "language": "en", "active": "1", "notes": json.dumps({"official": True, "source_type": "airline_newsroom"})}]
    entry = {"name": "Delta Air Lines Newsroom", "urls": ["https://www.delta.com/newsroom"], "source_type": "airline_ir", "region": "North America", "language": "en", "mode": "full"}
    merged, report = source_catalog.merge_expansion(rows, {"sources": [entry]}, TYPES)
    assert len(merged) == 1 and report["added"] == [] and report["merged_same_domain"] == ["Delta Air Lines Newsroom -> Delta News Hub"]
    assert "https://www.delta.com/newsroom" in json.loads(merged[0]["notes"])["discovery_urls"]
    assert merged[0]["status"] == "active" and merged[0]["source_type"] == "airline_ir"


def test_catalog_columns_and_values_are_valid():
    for row in source_catalog.read_rows():
        assert row["source_type"] in TYPES["types"] and row["status"] in TYPES["statuses"] and row["mode"] in TYPES["modes"]
        assert row["commercial_use_risk"] in {"", *TYPES["commercial_use_risks"]}
        assert row["timeout_s"].isdigit() and int(row["timeout_s"]) >= 1
        assert (row["status"] == "active") == (row["active"] == "1")
        assert row["official"] in {"true", "false"}


def test_tiers_follow_the_source_types_unless_a_row_says_otherwise():
    for row in source_catalog.read_rows():
        entry = next((e for e in EXPANSION["sources"] if e["name"] == row["name"]), None)
        if entry is None or entry.get("tier"):
            continue
        assert int(row["tier"]) == TYPES["types"][row["source_type"]]["tier"], row["name"]
    vendors = [row for row in source_catalog.read_rows() if row["source_type"] == "tech_vendor"]
    assert vendors and all(row["tier"] == "4" for row in vendors), "tech vendors stay on the lowest tier"


FEED_ONLY_NAMES = {"Reuters Aviation", "Bloomberg Aviation", "Financial Times Aviation", "The New York Times", "The Washington Post", "The Wall Street Journal", "Associated Press Aviation",
                   "The Economist", "Nikkei Asia", "The Air Current", "Aviation Week", "ch-aviation", "CAPA Centre for Aviation", "CNBC Airlines", "Cirium Thought Cloud", "OAG Blog", "AvHerald",
                   # wire services: terms restrict republishing, so only title, link and short summary are used
                   "PR Newswire Travel Sector", "PR Newswire Heavy Industry Sector", "GlobeNewswire Transportation Feed", "Business Wire Feeds",
                   "Google Alerts (wire headlines)"}
STANDARD_PRESS = {"FlightGlobal", "Simple Flying", "AeroTime", "Routes Online News", "PhocusWire", "China Travel News"}


def test_feed_only_is_limited_to_paywalled_or_restrictive_publishers():
    rows = {row["name"]: row for row in source_catalog.read_rows()}
    for entry in EXPANSION["sources"]:
        assert rows[entry["name"]]["mode"] == entry["mode"]
    assert {name for name, row in rows.items() if row["mode"] == "feed_only"} == FEED_ONLY_NAMES
    assert all(rows[name]["mode"] == "full" for name in STANDARD_PRESS), "open commercial press runs in the standard mode"


def test_languages_follow_the_agreed_rule():
    rows = {row["name"]: row for row in source_catalog.read_rows()}
    assert rows["SHGM News"]["language"] == "tr" and rows["KAP Public Disclosure"]["language"] == "en"


def test_the_six_sec_rows_carry_a_cik_and_the_agreed_items():
    sec = [row for row in source_catalog.read_rows() if json.loads(row["notes"]).get("cik")]
    assert len(sec) == 6 and all(json.loads(row["notes"])["edgar_items"] == ["2.02", "7.01", "8.01"] for row in sec)
