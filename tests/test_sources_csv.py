import csv
import sqlite3

import pytest

from api import _engine, source_registry


def read_csv_rows():
    with source_registry.SOURCES_CSV_PATH.open(encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def test_registry_database_is_built_from_the_csv(tmp_path):
    database = tmp_path / "registry.sqlite3"
    source_registry.sync_sources_from_csv(target_path=database)
    rows = read_csv_rows()
    weights = source_registry.load_registry_config()["tier_reliability_weights"]

    with sqlite3.connect(database) as connection:
        stored = {
            (name, url): (tier, weight, license_status, language, active)
            for name, url, tier, weight, license_status, language, active in connection.execute(
                "SELECT name, url, tier, reliability_weight, license_status, language, active FROM sources"
            )
        }

    assert len(stored) == len(rows)
    for row in rows:
        assert stored[(row["name"], row["url"])] == (
            int(row["tier"]), weights[row["tier"]], row["license_status"], row["language"], int(row["active"]),
        )
    assert sum(values[4] for values in stored.values()) == sum(1 for row in rows if row["status"] == "active")


def test_every_code_defined_source_is_in_the_csv_and_the_rest_are_catalog_rows():
    csv_rows = read_csv_rows()
    csv_keys = {(row["name"], row["url"]) for row in csv_rows}
    code_keys = {(source["name"], source["url"]) for source in _engine.get_builtin_source_records()}
    assert code_keys <= csv_keys, "a source defined in code is missing from config/sources.csv"
    code_names = {name for name, _ in code_keys}
    extra = [row for row in csv_rows if row["name"] not in code_names]
    assert extra and all(row["status"] in {"active", "no_extractable_feed", "no_public_feed", "disabled_blocked", "excluded_policy"} for row in extra)


def test_csv_sync_is_idempotent(tmp_path):
    database = tmp_path / "registry.sqlite3"
    source_registry.sync_sources_from_csv(target_path=database)
    source_registry.sync_sources_from_csv(target_path=database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == len(read_csv_rows())


def test_csv_active_flag_controls_ingestion(tmp_path):
    rows = read_csv_rows()
    disabled = next(row for row in rows if row["name"] == "Simple Flying")
    disabled["active"] = "0"
    disabled["status"] = "disabled_blocked"
    csv_path = tmp_path / "sources.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=source_registry.SOURCES_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    database = tmp_path / "registry.sqlite3"
    source_registry.sync_sources_from_csv(csv_path, database)

    active_names = {source["name"] for source in source_registry.load_active_sources(_engine.get_builtin_source_records(), database)}

    assert "Simple Flying" not in active_names
    assert "Delta News Hub" in active_names


def test_paid_source_cannot_be_activated_through_the_csv(tmp_path):
    rows = read_csv_rows()
    paid = next(row for row in rows if row["name"] == "Simple Flying")
    paid["license_status"], paid["active"], paid["status"] = "paid", "1", "active"
    csv_path = tmp_path / "sources.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=source_registry.SOURCES_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="paid sources cannot be active"):
        source_registry.sync_sources_from_csv(csv_path, tmp_path / "registry.sqlite3")
