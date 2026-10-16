"""Checks on the real config/entities seed: identity stability, coverage and the approved decisions."""

import csv
import io
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from api import entities


PROJECT_DIR = Path(__file__).resolve().parents[1]
ENTITY_RELATIVE_DIR = "config/entities"
MIN_ENTITIES_PER_REGION = 8
FIRST_COLUMN_FILES = ("groups.csv", "carriers.csv", "airports.csv", "aircraft_types.csv", "entity_history.csv")


@pytest.fixture(scope="module")
def data():
    return entities.load_all()


@pytest.fixture(scope="module")
def index():
    return entities.EntityIndex.from_csv()


def read_rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def head_version(relative_path):
    """The committed copy of a file, or None when git or the commit is unavailable."""
    try:
        result = subprocess.run(
            ["git", "show", f"HEAD:{relative_path}"], cwd=PROJECT_DIR, capture_output=True, text=True,
            encoding="utf-8", timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


@pytest.mark.parametrize("filename", FIRST_COLUMN_FILES)
def test_entity_id_is_the_first_column_of_every_entity_csv(filename):
    header = (PROJECT_DIR / ENTITY_RELATIVE_DIR / filename).read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header[0] == "entity_id"


def id_changes(committed_text, current_text):
    """(removed ids, ids that now point at another slug) between the committed and current CSV."""
    committed = {row["entity_id"]: row["slug"] for row in read_rows(committed_text)}
    current = {row["entity_id"]: row["slug"] for row in read_rows(current_text)}
    removed = sorted(set(committed) - set(current))
    changed = sorted(entity_id for entity_id, slug in committed.items() if entity_id in current and current[entity_id] != slug)
    return removed, changed


def csv_text(*pairs):
    return "entity_id,slug\n" + "".join(f"{entity_id},{slug}\n" for entity_id, slug in pairs)


def test_id_change_detection_catches_renumbering_removal_and_reuse():
    committed = csv_text(("carrier:000001", "lufthansa"), ("carrier:000002", "swiss"), ("carrier:000003", "austrian"))
    appended = committed + csv_text(("carrier:000004", "brussels")).split("\n", 1)[1]
    assert id_changes(committed, appended) == ([], [])

    swapped = csv_text(("carrier:000001", "swiss"), ("carrier:000002", "lufthansa"), ("carrier:000003", "austrian"))
    assert id_changes(committed, swapped) == ([], ["carrier:000001", "carrier:000002"])

    shifted = csv_text(("carrier:000002", "lufthansa"), ("carrier:000003", "swiss"), ("carrier:000004", "austrian"))
    assert id_changes(committed, shifted) == (["carrier:000001"], ["carrier:000002", "carrier:000003"])


@pytest.mark.parametrize("filename", ("groups.csv", "carriers.csv", "airports.csv", "aircraft_types.csv"))
def test_entity_ids_are_never_renumbered_or_removed(filename):
    committed = head_version(f"{ENTITY_RELATIVE_DIR}/{filename}")
    if committed is None:
        pytest.skip(f"{filename} is not committed yet; the check starts with the first commit")
    current = (PROJECT_DIR / ENTITY_RELATIVE_DIR / filename).read_text(encoding="utf-8")
    removed, changed = id_changes(committed, current)
    assert not removed, f"{filename}: committed ids removed (retire via history, never delete): {removed}"
    assert not changed, f"{filename}: committed ids now point at a different entity: {changed}"


def test_every_region_has_enough_carriers_and_airports(data):
    config = entities.load_sections_config()
    carrier_regions = Counter(carrier["region"] for carrier in data["carriers"])
    airport_regions = Counter(config["country_regions"][airport["country"]] for airport in data["airports"])
    for region in config["regions"]:
        assert carrier_regions[region] >= MIN_ENTITIES_PER_REGION, region
        assert airport_regions[region] >= MIN_ENTITIES_PER_REGION, region


def test_turkiye_is_in_europe(data):
    assert entities.load_sections_config()["country_regions"]["Türkiye"] == "Europe"
    by_slug = {carrier["slug"]: carrier for carrier in data["carriers"]}
    assert by_slug["turkish-airlines"]["region"] == by_slug["pegasus"]["region"] == "Europe"
    assert {a["iata"] for a in data["airports"] if a["country"] == "Türkiye"} >= {"IST", "SAW", "AYT", "ESB", "ADB"}


def brands_of(data, group_slug):
    group = next(g for g in data["groups"] if g["slug"] == group_slug)
    return {c["slug"] for c in data["carriers"] if c["parent_entity_id"] == group["entity_id"]}


def test_groups_link_their_brands_through_parent_entity_id(data):
    assert brands_of(data, "lufthansa-group") >= {"lufthansa", "swiss", "austrian-airlines", "brussels-airlines", "eurowings"}
    assert brands_of(data, "international-airlines-group") >= {"british-airways", "iberia", "vueling", "aer-lingus", "level"}
    assert brands_of(data, "air-france-klm-group") >= {"air-france", "klm", "transavia", "transavia-france"}


def test_a_group_tier_comes_from_the_sum_of_its_brands_not_its_largest(data):
    carriers = {c["slug"]: c for c in data["carriers"]}
    iag = next(g for g in data["groups"] if g["slug"] == "international-airlines-group")
    assert iag["metric_approx"] == sum(carriers[slug]["metric_approx"] for slug in brands_of(data, "international-airlines-group"))
    assert iag["tier"] == 1 and carriers["aer-lingus"]["tier"] > 1


def test_cargo_carriers_are_included_with_an_operator_type(data):
    types = {c["slug"]: c["operator_type"] for c in data["carriers"]}
    assert types["fedex-express"] == types["lufthansa-cargo"] == "cargo"
    assert types["emirates"] == "mixed" and types["delta-air-lines"] == "passenger"


def test_carrier_tier_uses_weighted_fleet_and_the_contract_regional_cap(data):
    for carrier in data["carriers"]:
        fleet = {"widebody": carrier["fleet_widebody"], "narrowbody": carrier["fleet_narrowbody"], "regional": carrier["fleet_regional"]}
        metric, tier, cargo_tier = entities.carrier_tiers(fleet, carrier["operator_type"], carrier["capacity_purchase"])
        if carrier["tier_override"] is None:
            assert (carrier["tier"], carrier["cargo_tier"]) == (tier, cargo_tier), carrier["slug"]
        assert carrier["metric_approx"] == pytest.approx(metric)


def test_cargo_operators_have_a_cargo_tier_and_no_passenger_tier(data):
    cargo = [c for c in data["carriers"] if c["operator_type"] == "cargo"]
    assert {"fedex-express", "ups-airlines", "atlas-air", "lufthansa-cargo"} <= {c["slug"] for c in cargo}
    assert all(c["tier"] is None and c["cargo_tier"] in (1, 2, 3, 4) for c in cargo)
    assert all(c["cargo_tier"] is None and c["tier"] in (1, 2, 3, 4) for c in data["carriers"] if c["operator_type"] != "cargo")


def test_contract_regionals_are_flagged_and_never_tier_one(data):
    by_slug = {c["slug"]: c for c in data["carriers"]}
    for slug in ("skywest-airlines", "republic-airways", "envoy-air", "psa-airlines", "endeavor-air"):
        assert by_slug[slug]["capacity_purchase"] == 1, slug
    assert by_slug["skywest-airlines"]["tier"] == 2 and by_slug["skywest-airlines"]["metric_approx"] >= 200
    assert all(c["tier"] >= 2 for c in data["carriers"] if c["capacity_purchase"] and c["tier"])


def test_group_tiers_use_the_doubled_thresholds(data):
    for group_row in data["groups"]:
        if group_row["tier_override"] is None:
            assert group_row["tier"] == entities.group_tier(group_row["metric_approx"])
    assert {g["tier"] for g in data["groups"]} > {1}   # the doubled thresholds make groups discriminate again


def test_airport_tier_uses_annual_passengers_and_tier_one_two_are_hubs(data):
    for airport in data["airports"]:
        if airport["tier_override"] is None:
            assert airport["tier"] == entities.airport_tier(airport["metric_approx"])
        if airport["tier"] <= 2:
            assert airport["is_hub"] == 1, airport["slug"]
    assert next(a for a in data["airports"] if a["iata"] == "IST")["is_hub"] == 1


def test_verified_rows_state_their_source_and_check_date(data):
    verified = [c for c in data["carriers"] if c["verified_at"]]
    assert len(verified) >= 40
    assert all(c["verification_source"].startswith("http") and c["verified_at"] == "2026-10-16" for c in verified)


def test_every_hand_set_tier_has_a_reason(data):
    for collection in (data["groups"], data["carriers"], data["airports"]):
        assert all(item["override_reason"] for item in collection if item["tier_override"] is not None)


def test_seed_history_links_a_retired_name_to_the_surviving_entity(index):
    assert [c["slug"] for c in index.find("Vistara merges into the Air India network")["carriers"]] == ["air-india"]
    assert [c["slug"] for c in index.find("AnadoluJet flights")["carriers"]] == ["ajet"]


def test_seed_matches_turkish_forms_end_to_end(index):
    found = index.find("THY'nin İstanbul Havalimanı'ndaki CFM motor anlaşması")
    assert [c["slug"] for c in found["carriers"]] == ["turkish-airlines"]
    assert [a["slug"] for a in found["airports"]] == ["istanbul-airport"]
    assert index.assign_sections(found, None, "THY'nin İstanbul Havalimanı'ndaki CFM motor anlaşması") == (
        "Europe", ["Manufacturers & Supply Chain"],
    )


def test_seed_group_name_does_not_double_count_brands(index):
    found = index.find("Air France-KLM and Lufthansa Group report results")
    assert [g["slug"] for g in found["groups"]] == ["air-france-klm-group", "lufthansa-group"]
    assert found["carriers"] == []
