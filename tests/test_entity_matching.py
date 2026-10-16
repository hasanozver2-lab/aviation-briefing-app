import copy
import csv
import sqlite3

import pytest

from api import entities, market_data, text_match


def carrier(entity_id, slug, iata, icao, name, region, operator="passenger", wide=0, narrow=0, regional=0,
            parent="", aliases="", alliance="", capacity_purchase=0, **extra):
    row = {column: "" for column in entities.COLUMNS["carriers"]}
    row.update({
        "entity_id": entity_id, "slug": slug, "parent_entity_id": parent, "iata": iata, "icao": icao, "name": name,
        "aliases": aliases, "region": region, "alliance": alliance, "operator_type": operator,
        "metric_approx": "0", "fleet_widebody": wide, "fleet_narrowbody": narrow, "fleet_regional": regional,
        "capacity_purchase": capacity_purchase, "needs_verification": 0,
    })
    row.update(extra)
    return row


def airport(entity_id, slug, iata, icao, name, city, country, passengers, aliases="", hub=0, **extra):
    row = {column: "" for column in entities.COLUMNS["airports"]}
    row.update({
        "entity_id": entity_id, "slug": slug, "iata": iata, "icao": icao, "name": name, "city": city,
        "country": country, "aliases": aliases, "is_hub": hub, "metric_approx": passengers, "needs_verification": 0,
    })
    row.update(extra)
    return row


def group(entity_id, slug, name, region="Europe", aliases="", **extra):
    row = {column: "" for column in entities.COLUMNS["groups"]}
    row.update({"entity_id": entity_id, "slug": slug, "name": name, "aliases": aliases, "region": region,
                "metric_approx": "0", "needs_verification": 0})
    row.update(extra)
    return row


def base_groups():
    return [
        group("group:000001", "lufthansa-group", "Lufthansa Group", aliases="Lufthansa Gruppe"),
        group("group:000002", "air-france-klm-group", "Air France-KLM", aliases="AF-KLM"),
    ]


def base_carriers():
    eu, am = "Europe", "Americas"
    return [
        carrier("carrier:000001", "turkish-airlines", "TK", "THY", "Turkish Airlines", eu, wide=130, narrow=245,
                aliases="THY|Türk Hava Yolları", alliance="Star Alliance"),
        carrier("carrier:000002", "lufthansa", "LH", "DLH", "Lufthansa", eu, wide=100, narrow=205, parent="group:000001"),
        carrier("carrier:000003", "swiss", "LX", "SWR", "SWISS International Air Lines", eu, wide=26, narrow=64,
                parent="group:000001", aliases="=SWISS"),
        carrier("carrier:000004", "pegasus", "PC", "PGT", "Pegasus Airlines", eu, narrow=115, aliases="Pegasus"),
        carrier("carrier:000005", "british-airways", "BA", "BAW", "British Airways", eu, wide=125, narrow=140),
        carrier("carrier:000006", "american-airlines", "AA", "AAL", "American Airlines", am, wide=107, narrow=855),
        carrier("carrier:000007", "delta-air-lines", "DL", "DAL", "Delta Air Lines", am, wide=165, narrow=825, aliases="Delta"),
        carrier("carrier:000008", "sas", "SK", "SAS", "Scandinavian Airlines", eu, wide=12, narrow=75, regional=30, aliases="SAS"),
        carrier("carrier:000009", "ana", "NH", "ANA", "All Nippon Airways", "Asia-Pacific", wide=95, narrow=100, aliases="ANA"),
        carrier("carrier:000010", "emirates", "EK", "UAE", "Emirates", "Middle East & Gulf", operator="mixed", wide=255),
        carrier("carrier:000011", "lufthansa-cargo", "", "GEC", "Lufthansa Cargo", eu, operator="cargo", wide=60,
                regional=40, parent="group:000001", aliases="LH Cargo"),
        carrier("carrier:000012", "air-france", "AF", "AFR", "Air France", eu, wide=92, narrow=125, parent="group:000002"),
        carrier("carrier:000013", "klm", "KL", "KLM", "KLM", eu, wide=42, narrow=47, parent="group:000002"),
        carrier("carrier:000014", "tiny-air", "TY", "TNY", "Tiny Air", "Africa", narrow=5),
        carrier("carrier:000015", "big-regional", "BR", "BRG", "Big Regional", am, regional=480, capacity_purchase=1),
        carrier("carrier:000016", "small-regional", "SR", "SRG", "Small Regional", am, regional=120, capacity_purchase=1),
    ]


def base_airports():
    return [
        airport("airport:000001", "istanbul-airport", "IST", "LTFM", "Istanbul Airport", "Istanbul", "Türkiye", 80,
                aliases="İstanbul Havalimanı|Istanbul Havalimani", hub=1),
        airport("airport:000002", "amsterdam-schiphol", "AMS", "EHAM", "Amsterdam Schiphol", "Amsterdam", "Netherlands", 67,
                aliases="Schiphol", hub=1),
        airport("airport:000003", "paris-charles-de-gaulle", "CDG", "LFPG", "Paris Charles de Gaulle", "Paris", "France", 70,
                aliases="Charles de Gaulle", hub=1),
        airport("airport:000004", "john-f-kennedy-international", "JFK", "KJFK", "John F. Kennedy International", "New York",
                "United States", 63, hub=1),
        airport("airport:000005", "ataturk-airport", "ISL", "LTBA", "Atatürk Airport", "Istanbul", "Türkiye", 0,
                aliases="Atatürk Havalimanı"),
        airport("airport:000006", "small-field", "SMF", "KSMF", "Small Field", "Smalltown", "United States", 3),
    ]


AIRCRAFT_CSV = """entity_id,slug,code,family,manufacturer,aliases
aircraft:000001,a220,A220,A220,Airbus,Airbus A220
aircraft:000002,b737-max-8,B38M,737 MAX,Boeing,737 MAX 8|Boeing 737 MAX 8
aircraft:000003,b737-max,B737MAX,737 MAX,Boeing,737 MAX|Boeing 737 MAX
"""

HISTORY_HEADER = "entity_id,kind,value,valid_from,valid_to,needs_verification\n"

HISTORY_CSV = """entity_id,kind,value,valid_from,valid_to,needs_verification
carrier:000004,alias,Pegasus Hava Yollari AS,,2020-01-01,0
airport:000001,iata,IST,2019-04-06,,0
airport:000005,iata,IST,,2019-04-06,0
"""

COUNTRY_REGIONS = {"Türkiye": "Europe", "Netherlands": "Europe", "France": "Europe", "United States": "Americas"}


def to_csv(kind, rows):
    import io
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=entities.COLUMNS[kind], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def write_entity_dir(directory, groups=None, carriers=None, airports=None, aircraft=AIRCRAFT_CSV,
                     history=HISTORY_CSV, recompute=True):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "groups.csv").write_text(to_csv("groups", groups if groups is not None else base_groups()), encoding="utf-8")
    (directory / "carriers.csv").write_text(to_csv("carriers", carriers if carriers is not None else base_carriers()), encoding="utf-8")
    (directory / "airports.csv").write_text(to_csv("airports", airports if airports is not None else base_airports()), encoding="utf-8")
    (directory / "aircraft_types.csv").write_text(aircraft, encoding="utf-8")
    (directory / "entity_history.csv").write_text(history, encoding="utf-8")
    if recompute:
        entities.recompute_derived_columns(directory)
    return directory


def sections_config():
    config = entities.load_sections_config()
    config["country_regions"] = COUNTRY_REGIONS
    return config


def load(directory):
    return entities.load_all(directory, sections_config())


@pytest.fixture
def entity_dir(tmp_path):
    return write_entity_dir(tmp_path / "entities")


@pytest.fixture
def index(entity_dir):
    return entities.EntityIndex.from_csv(entity_dir, sections_config())


def slugs(index, title, description="", kind="carriers"):
    return [item["slug"] for item in index.find(title, description)[kind]]


# --- Turkish case handling -------------------------------------------------

def test_turkish_lowercase_maps_dotted_and_dotless_i_correctly():
    assert text_match.turkish_lower("İSTANBUL") == "istanbul"
    assert text_match.turkish_lower("ISPARTA") == "ısparta"
    assert text_match.turkish_lower("IŞIK") == "ışık"
    # Python's default lowercase gets İ wrong, which is why turkish_lower exists.
    assert "İ".lower() != "i"


def test_fold_makes_all_casings_of_a_turkish_name_equal_and_keeps_length():
    assert text_match.fold("HAVALİMANI") == text_match.fold("havalimanı") == text_match.fold("HAVALIMANI")
    assert text_match.fold("Sabiha Gökçen") == text_match.fold("SABİHA GÖKÇEN") == "sabiha gokcen"
    assert len(text_match.fold("İSTANBUL HAVALİMANI'NDA")) == len("İSTANBUL HAVALİMANI'NDA")


# --- Turkish apostrophe suffixes --------------------------------------------

@pytest.mark.parametrize("title, expected", [
    ("THY'nin yeni uçakları teslim alındı", ["turkish-airlines"]),
    ("THY’nin yeni uçakları teslim alındı", ["turkish-airlines"]),
    ("Lufthansa'nın grev kararı", ["lufthansa"]),
    ("Pegasus'un yeni hattı açıldı", ["pegasus"]),
    ("Delta's winter schedule", ["delta-air-lines"]),
    ("LUFTHANSA'NIN HİSSELERİ YÜKSELDİ", ["lufthansa"]),
])
def test_apostrophe_suffixes_are_tolerated_for_carriers(index, title, expected):
    assert slugs(index, title) == expected


@pytest.mark.parametrize("title", [
    "İstanbul Havalimanı'nda yoğunluk arttı",
    "İSTANBUL HAVALİMANI'NDA YOĞUNLUK ARTTI",
    "ISTANBUL HAVALIMANI'NDA YOGUNLUK ARTTI",
    "Istanbul Airport's third runway opens",
])
def test_apostrophe_suffixes_and_case_are_tolerated_for_airports(index, title):
    assert slugs(index, title, kind="airports") == ["istanbul-airport"]


def test_words_that_merely_start_with_an_alias_do_not_match(index):
    assert slugs(index, "Pegasusland amusement park opens") == []
    assert slugs(index, "Deltaic sediments study") == []


# --- short codes and acronyms -------------------------------------------------

@pytest.mark.parametrize("title", [
    "BA117 diverted to Manchester",
    "BA 117 diverted to Manchester",
    "BA flights cancelled this weekend",
    "BA's pilots vote on strike",
])
def test_short_carrier_code_matches_in_operational_context(index, title):
    assert slugs(index, title) == ["british-airways"]


@pytest.mark.parametrize("title", [
    "BA graduates hired at record rate",
    "Boeing (BA) shares fall after delivery halt",
    "AA 2025 results beat estimates",
    "ba flights are not an airline code in lowercase",
])
def test_short_carrier_code_is_ignored_without_context(index, title):
    assert slugs(index, title) == []


def test_case_sensitive_acronyms_do_not_collide_with_ordinary_words(index):
    assert slugs(index, "SAS cancels Copenhagen flights") == ["sas"]
    assert slugs(index, "Her sas was spilled in the kitchen") == []
    assert slugs(index, "ANA orders new widebodies") == ["ana"]
    assert slugs(index, "Ana hat üzerinde bakım çalışması") == []


def test_equals_prefix_forces_case_sensitivity_for_longer_names(index):
    assert slugs(index, "SWISS cancels Zurich flights") == ["swiss"]
    assert slugs(index, "Swiss franc strengthens against the euro") == []


def test_airport_codes_need_route_parentheses_or_number_context(index):
    assert slugs(index, "Heavy traffic at (IST) today", kind="airports") == ["istanbul-airport"]
    assert sorted(slugs(index, "New IST-AMS frequency added", kind="airports")) == ["amsterdam-schiphol", "istanbul-airport"]
    assert sorted(slugs(index, "IST 1.530 vs AMS 1.386 vs CDG 1.361 weekly flights", kind="airports")) == [
        "amsterdam-schiphol", "istanbul-airport", "paris-charles-de-gaulle",
    ]
    assert slugs(index, "The IST study was published", kind="airports") == []


def test_matches_are_ranked_title_first_then_by_position(index):
    assert slugs(index, "Delta and Lufthansa expand", "Pegasus also adds routes") == ["delta-air-lines", "lufthansa", "pegasus"]
    assert slugs(index, "Airline roundup", "Pegasus adds routes while Delta cuts") == ["pegasus", "delta-air-lines"]


# --- groups, exclusions, history ------------------------------------------------

def test_group_name_shadows_its_own_brand_aliases(index):
    found = index.find("Air France-KLM expands while Lufthansa Group posts results")
    assert [g["slug"] for g in found["groups"]] == ["air-france-klm-group", "lufthansa-group"]
    assert found["carriers"] == []


def test_brand_named_separately_is_still_found_next_to_its_group(index):
    found = index.find("Air France-KLM results; Air France adds flights")
    assert [c["slug"] for c in found["carriers"]] == ["air-france"]
    assert found["carriers"][0]["group_entity_id"] == "group:000002"


def test_longer_alias_of_another_entity_shadows_the_shorter_one(index):
    assert slugs(index, "Lufthansa Cargo orders freighters") == ["lufthansa-cargo"]


def test_exclusion_phrases_stop_country_names_matching_airlines(index):
    assert slugs(index, "United Arab Emirates economy grows") == []
    assert slugs(index, "Emirates adds Dubai flights; United Arab Emirates economy grows") == ["emirates"]
    assert slugs(index, "Pegasus spyware report") == []
    # An exclusion masks only its own phrase; a separate mention still counts.
    assert slugs(index, "Pegasus spyware hits phones; Pegasus adds flights") == ["pegasus"]


def test_exclusions_file_covers_the_known_collisions():
    phrases = entities._load_json(entities.EXCLUSIONS_PATH)["phrases"]
    assert "United Arab Emirates" in phrases and "Pegasus spyware" in phrases


def test_historical_names_still_match_the_current_entity(index):
    assert slugs(index, "Pegasus Hava Yollari AS yeni hat açtı") == ["pegasus"]


def test_matches_carry_the_permanent_entity_id(index):
    found = index.find("THY and IST 1.530 and Airbus A220")
    assert found["carriers"][0]["entity_id"] == "carrier:000001"
    assert found["airports"][0]["entity_id"] == "airport:000001"
    assert found["aircraft"][0]["entity_id"] == "aircraft:000001"


# --- identity, loading and validation -------------------------------------------

def test_alias_shared_by_two_entities_is_rejected(tmp_path):
    carriers = base_carriers() + [carrier("carrier:000017", "delta-cargo", "", "DCG", "Delta Cargo", "Americas",
                                          operator="cargo", narrow=5, aliases="Delta")]
    directory = write_entity_dir(tmp_path / "bad", carriers=carriers)
    with pytest.raises(ValueError, match="shared by"):
        entities.EntityIndex.from_csv(directory, sections_config())


def mutated(**changes):
    carriers = base_carriers()
    carriers[-1].update(changes)
    return carriers


@pytest.mark.parametrize("changes, message", [
    ({"region": "Atlantis"}, "unknown region"),
    ({"entity_id": "airport:000016"}, "invalid entity_id"),
    ({"entity_id": "carrier:16"}, "invalid entity_id"),
    ({"entity_id": "carrier:000015"}, "duplicate entity_id"),
    ({"slug": "klm"}, "duplicate slug"),
    ({"operator_type": "freight"}, "invalid operator_type"),
    ({"parent_entity_id": "group:000099"}, "unknown parent_entity_id"),
    ({"iata": "TK"}, "duplicate iata"),
    ({"capacity_purchase": "2"}, "capacity_purchase must be 0 or 1"),
])
def test_invalid_carrier_rows_fail_loudly(tmp_path, changes, message):
    directory = write_entity_dir(tmp_path / "bad", carriers=mutated(**changes))
    with pytest.raises(ValueError, match=message):
        load(directory)


def test_entity_id_must_be_the_first_column(tmp_path):
    directory = write_entity_dir(tmp_path / "bad")
    (directory / "groups.csv").write_text(
        "slug,entity_id,name,aliases,region,tier,metric_approx,needs_verification,tier_override,override_reason\n"
        "lufthansa-group,group:000001,Lufthansa Group,,Europe,1,1,0,,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="entity_id must be the first column"):
        load(directory)


def test_airport_country_without_region_fails_loudly(tmp_path):
    airports = base_airports() + [airport("airport:000007", "atlantis-intl", "ATL1", "XXXX", "Atlantis Intl", "Atlantis", "Atlantis", 1)]
    directory = write_entity_dir(tmp_path / "bad", airports=airports)
    with pytest.raises(ValueError, match="no region"):
        load(directory)


def test_group_without_member_brands_fails_loudly(tmp_path):
    groups = base_groups() + [group("group:000003", "orphan-group", "Orphan Group")]
    directory = write_entity_dir(tmp_path / "bad", groups=groups)
    with pytest.raises(ValueError, match="no member brands"):
        load(directory)


@pytest.mark.parametrize("row, message", [
    ("carrier:000004,alias,Pegasus Old,2020-01-01,2019-01-01,0", "after valid_to"),
    ("carrier:000099,alias,Ghost,,,0", "unknown entity_id"),
    ("carrier:000004,alias,Pegasus Old,01/01/2020,,0", "YYYY-MM-DD"),
    ("carrier:000004,nickname,Pegasus Old,,,0", "invalid kind"),
])
def test_invalid_history_rows_fail_loudly(tmp_path, row, message):
    directory = write_entity_dir(tmp_path / "bad", history=HISTORY_CSV + row + "\n")
    with pytest.raises(ValueError, match=message):
        load(directory)


def test_repository_entity_csvs_load():
    entities.EntityIndex.from_csv()


# --- tiers ------------------------------------------------------------------------

def test_weighted_fleet_counts_widebody_double_and_regional_half():
    assert entities.weighted_fleet(10, 20, 8) == 10 * 2 + 20 + 8 * 0.5


def test_cargo_weighting_counts_regional_feeders_at_a_quarter():
    assert entities.weighted_fleet(10, 20, 8, cargo=True) == 10 * 2 + 20 + 8 * 0.25


@pytest.mark.parametrize("value, tier", [(200, 1), (199.9, 2), (100, 2), (99.5, 3), (50, 3), (49.5, 4), (0, 4)])
def test_carrier_tier_boundaries(value, tier):
    assert entities.carrier_tier(value) == tier


@pytest.mark.parametrize("value, tier", [(400, 1), (399.9, 2), (200, 2), (199.9, 3), (100, 3), (99.9, 4)])
def test_group_tier_thresholds_are_double_the_brand_thresholds(value, tier):
    assert entities.group_tier(value) == tier


@pytest.mark.parametrize("millions, tier", [(50, 1), (49.9, 2), (25, 2), (24.9, 3), (10, 3), (9.9, 4)])
def test_airport_tier_boundaries(millions, tier):
    assert entities.airport_tier(millions) == tier


def test_tiers_are_derived_per_brand_and_groups_sum_their_passenger_brands(entity_dir):
    data = load(entity_dir)
    by_slug = {c["slug"]: c for c in data["carriers"]}
    assert by_slug["turkish-airlines"]["metric_approx"] == 130 * 2 + 245 and by_slug["turkish-airlines"]["tier"] == 1
    assert by_slug["swiss"]["metric_approx"] == 26 * 2 + 64 and by_slug["swiss"]["tier"] == 2
    assert by_slug["tiny-air"]["tier"] == 4
    lufthansa_group = next(g for g in data["groups"] if g["slug"] == "lufthansa-group")
    passenger_members = [c for c in data["carriers"] if c["parent_entity_id"] == "group:000001" and c["operator_type"] != "cargo"]
    assert lufthansa_group["metric_approx"] == sum(c["metric_approx"] for c in passenger_members) == 405 + 116
    assert lufthansa_group["tier"] == 1


def test_group_tier_uses_the_group_thresholds(tmp_path):
    carriers = [
        carrier("carrier:000001", "a-air", "AA", "AAA", "A Air", "Europe", wide=60, narrow=100, parent="group:000001"),
        carrier("carrier:000002", "b-air", "BB", "BBB", "B Air", "Europe", wide=20, narrow=50, parent="group:000001"),
    ]
    directory = write_entity_dir(tmp_path / "g", groups=[group("group:000001", "ab-group", "AB Group")],
                                 carriers=carriers, airports=[],
                                 history=HISTORY_HEADER)
    data = load(directory)
    assert data["groups"][0]["metric_approx"] == 220 + 90
    assert data["groups"][0]["tier"] == 2   # 310 is tier 1 for a brand but tier 2 for a group
    assert min(c["tier"] for c in data["carriers"]) == 1


def test_contract_regional_cannot_rank_above_tier_two(entity_dir):
    by_slug = {c["slug"]: c for c in load(entity_dir)["carriers"]}
    assert by_slug["big-regional"]["metric_approx"] == 240
    assert by_slug["big-regional"]["tier"] == 2          # would be 1 without capacity_purchase
    assert by_slug["small-regional"]["tier"] == 3        # the cap never lifts a lower tier


def test_cargo_operators_leave_the_passenger_tier_and_get_a_cargo_tier(entity_dir):
    data = load(entity_dir)
    cargo = next(c for c in data["carriers"] if c["slug"] == "lufthansa-cargo")
    assert cargo["tier"] is None
    assert cargo["metric_approx"] == 60 * 2 + 40 * 0.25 == 130
    assert cargo["cargo_tier"] == 2
    passenger = next(c for c in data["carriers"] if c["slug"] == "lufthansa")
    assert passenger["cargo_tier"] is None and passenger["tier"] == 1


def test_cargo_brands_do_not_count_toward_the_group_passenger_tier(entity_dir):
    data = load(entity_dir)
    group_row = next(g for g in data["groups"] if g["slug"] == "lufthansa-group")
    assert group_row["metric_approx"] == 405 + 116   # 130 of Lufthansa Cargo excluded


def test_operator_type_is_stored(entity_dir):
    types = {c["slug"]: c["operator_type"] for c in load(entity_dir)["carriers"]}
    assert types["lufthansa-cargo"] == "cargo" and types["emirates"] == "mixed" and types["lufthansa"] == "passenger"


def test_stale_derived_values_are_rejected_and_recompute_repairs_them(tmp_path):
    carriers = mutated(tier="1", metric_approx="999")
    directory = write_entity_dir(tmp_path / "stale", carriers=carriers, recompute=False)
    with pytest.raises(ValueError, match="recompute_entity_tiers"):
        load(directory)
    entities.recompute_derived_columns(directory)
    assert next(c for c in load(directory)["carriers"] if c["slug"] == "small-regional")["tier"] == 3


def test_a_cargo_row_with_a_passenger_tier_is_rejected(tmp_path):
    carriers = base_carriers()
    cargo = next(c for c in carriers if c["slug"] == "lufthansa-cargo")
    directory = write_entity_dir(tmp_path / "bad", carriers=carriers)
    rows = list(csv.DictReader((directory / "carriers.csv").open(encoding="utf-8")))
    for row in rows:
        if row["slug"] == cargo["slug"]:
            row["tier"] = "2"
    with (directory / "carriers.csv").open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=entities.COLUMNS["carriers"])
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="recompute_entity_tiers"):
        load(directory)


# --- manual overrides ----------------------------------------------------------------

def test_override_sets_the_effective_tier_and_keeps_the_reason(tmp_path):
    carriers = mutated(tier_override="1", override_reason="Largest regional partner by network share")
    directory = write_entity_dir(tmp_path / "o", carriers=carriers)
    row = next(c for c in load(directory)["carriers"] if c["slug"] == "small-regional")
    assert row["tier"] == 1 and row["tier_override"] == 1 and "network share" in row["override_reason"]


def test_override_without_a_reason_fails_loudly(tmp_path):
    directory = write_entity_dir(tmp_path / "o", carriers=mutated(tier_override="1"))
    with pytest.raises(ValueError, match="without override_reason"):
        load(directory)


def test_override_outside_one_to_four_fails_loudly(tmp_path):
    directory = write_entity_dir(tmp_path / "o", carriers=mutated(tier_override="7", override_reason="typo"))
    with pytest.raises(ValueError, match="tier_override must be 1-4"):
        load(directory)


def test_cargo_override_applies_to_the_cargo_tier(tmp_path):
    carriers = base_carriers()
    next(c for c in carriers if c["slug"] == "lufthansa-cargo").update(tier_override="1", override_reason="Fleet page predates deliveries")
    directory = write_entity_dir(tmp_path / "o", carriers=carriers)
    cargo = next(c for c in load(directory)["carriers"] if c["slug"] == "lufthansa-cargo")
    assert cargo["cargo_tier"] == 1 and cargo["tier"] is None


def test_airport_and_group_overrides_need_a_reason_too(tmp_path):
    airports = base_airports()
    airports[-1].update(tier_override="2")
    directory = write_entity_dir(tmp_path / "a", airports=airports)
    with pytest.raises(ValueError, match="without override_reason"):
        load(directory)
    groups = base_groups()
    groups[0].update(tier_override="3")
    directory = write_entity_dir(tmp_path / "g", groups=groups)
    with pytest.raises(ValueError, match="without override_reason"):
        load(directory)


# --- hubs -------------------------------------------------------------------------

def test_tier_one_and_two_airports_must_be_hubs(tmp_path):
    airports = base_airports()
    airports[1]["is_hub"] = 0                      # Schiphol, 67 M passengers, tier 1
    directory = write_entity_dir(tmp_path / "h", airports=airports, recompute=False)
    directory_rows = entities._read_raw(directory / "airports.csv", entities.COLUMNS["airports"])[1]
    assert directory_rows[1]["is_hub"] == "0"
    entities.recompute_derived_columns(directory)   # only metric/tier are written; hub flag repaired too
    assert next(a for a in load(directory)["airports"] if a["slug"] == "amsterdam-schiphol")["is_hub"] == 1


def test_a_stale_non_hub_tier_one_airport_is_rejected(tmp_path):
    directory = write_entity_dir(tmp_path / "h")
    rows = list(csv.DictReader((directory / "airports.csv").open(encoding="utf-8")))
    rows[1]["is_hub"] = "0"
    with (directory / "airports.csv").open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=entities.COLUMNS["airports"])
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="must be is_hub=1"):
        load(directory)


def test_small_airports_keep_their_own_hub_flag(entity_dir):
    airports = {a["slug"]: a for a in load(entity_dir)["airports"]}
    assert airports["small-field"]["is_hub"] == 0 and airports["amsterdam-schiphol"]["is_hub"] == 1


# --- SQLite -----------------------------------------------------------------------

def test_sync_entities_is_idempotent_and_mirrors_the_csv(tmp_path, entity_dir):
    database = tmp_path / "pipeline.sqlite3"
    first = entities.sync_entities(database, entity_dir, sections_config())
    second = entities.sync_entities(database, entity_dir, sections_config())

    assert first == second == {"groups": 2, "carriers": 16, "airports": 6, "aircraft_types": 3, "history": 3}
    with sqlite3.connect(database) as connection:
        thy = connection.execute(
            "SELECT entity_id, iata, name, region, tier, fleet_widebody, operator_type, aliases_json FROM carriers WHERE slug = 'turkish-airlines'"
        ).fetchone()
        parent = connection.execute("SELECT parent_entity_id FROM carriers WHERE slug = 'swiss'").fetchone()[0]
        cargo = connection.execute("SELECT tier, cargo_tier FROM carriers WHERE slug = 'lufthansa-cargo'").fetchone()
        capacity = connection.execute("SELECT capacity_purchase, tier FROM carriers WHERE slug = 'big-regional'").fetchone()
        history = connection.execute("SELECT COUNT(*) FROM entity_history WHERE entity_id = 'airport:000001'").fetchone()[0]
    assert thy[:7] == ("carrier:000001", "TK", "Turkish Airlines", "Europe", 1, 130, "passenger")
    assert "Türk Hava Yolları" in thy[7]
    assert parent == "group:000001"
    assert cargo == (None, 2)
    assert capacity == (1, 2)
    assert history == 1


def test_verification_columns_round_trip(tmp_path):
    carriers = mutated(verification_source="https://example.com/fleet (airline, as of 2026-10)", verified_at="2026-10-16")
    directory = write_entity_dir(tmp_path / "v", carriers=carriers)
    database = tmp_path / "pipeline.sqlite3"
    entities.sync_entities(database, directory, sections_config())
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT verification_source, verified_at FROM carriers WHERE slug = 'small-regional'").fetchone()
    assert row == ("https://example.com/fleet (airline, as of 2026-10)", "2026-10-16")


def test_sync_removes_rows_deleted_from_the_csv(tmp_path):
    carriers = [c for c in base_carriers() if c["slug"] != "tiny-air"]
    directory = write_entity_dir(tmp_path / "e")
    database = tmp_path / "pipeline.sqlite3"
    entities.sync_entities(database, directory, sections_config())
    smaller = write_entity_dir(tmp_path / "smaller", carriers=carriers)
    entities.sync_entities(database, smaller, sections_config())
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM carriers").fetchone()[0] == 15


# --- section assignment and secondary tags --------------------------------------

def sections_for(index, title, description="", event_type=None):
    found = index.find(title, description)
    return index.assign_sections(found, event_type, title, description)


def test_section_follows_carrier_region_not_source_language(index):
    assert sections_for(index, "THY'nin yeni hattı")[0] == "Europe"
    assert sections_for(index, "Emirates adds Houston flights")[0] == "Middle East & Gulf"
    assert sections_for(index, "ANA orders new widebodies")[0] == "Asia-Pacific"
    assert sections_for(index, "American Airlines expands Dallas hub")[0] == "Americas"


def test_section_uses_airport_country_when_no_carrier_is_named(index):
    assert sections_for(index, "Heavy delays at (JFK) this evening") == ("Americas", [])


def test_regulator_and_airspace_events_take_priority_and_keep_the_region_as_a_tag(index):
    assert sections_for(index, "FAA orders inspections of Delta jets") == ("Regulation & Airspace", ["Americas"])
    assert sections_for(index, "Lufthansa reroutes flights", event_type="geopolitics_airspace") == ("Regulation & Airspace", ["Europe"])


def test_manufacturer_story_without_carrier_goes_to_supply_chain(index):
    assert sections_for(index, "Airbus A220 order announced by lessor") == ("Manufacturers & Supply Chain", [])
    assert sections_for(index, "Boeing halts deliveries amid supply chain shortage") == ("Manufacturers & Supply Chain", [])


def test_engine_deal_is_europe_primary_with_supply_chain_secondary_tag(index):
    assert sections_for(index, "THY signs 600-engine deal with CFM") == ("Europe", ["Manufacturers & Supply Chain"])


def test_story_spanning_regions_lists_the_other_regions_as_tags(index):
    primary, secondary = sections_for(index, "Delta and Emirates deepen codeshare while Lufthansa watches")
    assert primary == "Americas"
    assert set(secondary) == {"Middle East & Gulf", "Europe"}


def test_unmatched_story_is_explicitly_unassigned(index):
    assert sections_for(index, "Industry gathers for annual conference") == ("Other", [])


def test_annotate_articles_attaches_entities_section_and_tags(index):
    articles = [{"title": "THY signs deal with CFM", "description": "", "event_type": None}]
    entities.annotate_articles(articles, index)
    assert articles[0]["entities"]["carriers"][0]["entity_id"] == "carrier:000001"
    assert articles[0]["region_section"] == "Europe"
    assert articles[0]["secondary_tags"] == ["Manufacturers & Supply Chain"]
    assert entities.compact_codes(articles[0]["entities"]) == {"groups": [], "carriers": ["TK"], "airports": [], "aircraft": []}


# --- event_type substring regressions ----------------------------------------

@pytest.mark.parametrize("text", [
    "Okur sayısı artıyor, havayolu yolcuları memnun",   # "kur" inside "okur"
    "The task force reviewed airline schedules",         # "ask" inside "task"
    "Saf altın fiyatı yükseldi",                         # Turkish "saf" (pure), not SAF fuel
    "Real estate deal near airport",                     # "real" is not the Brazilian real
    "Airline warns of staff shortage toward winter",     # "war" inside "toward"
])
def test_short_terms_no_longer_match_inside_other_words(text):
    assert market_data.classify_event_type(text) is None


@pytest.mark.parametrize("text, expected", [
    ("SAF mandate lifts jet fuel costs", "fuel_energy"),
    ("ASK up 5% while load factor improves", "macro_demand"),
    ("Brazilian real weakens against the dollar", "fx_currency"),
    ("THY için döviz kuru ve dolar etkisi", "fx_currency"),
    ("Jet yakıtı zamlandı", "fuel_energy"),
    ("Missile strike closes airspace for airlines", "geopolitics_airspace"),
    ("Airline shares drop on analyst downgrade", "capital_markets"),
])
def test_intended_terms_still_classify(text, expected):
    assert market_data.classify_event_type(text)["event_type"] == expected


def test_geopolitical_term_without_aviation_context_is_still_ignored():
    assert market_data.classify_event_type("Sanctions on steel imports widen") is None
