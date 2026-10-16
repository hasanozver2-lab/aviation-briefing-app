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

    assert len(stored) == len(rows) == 39
    for row in rows:
        assert stored[(row["name"], row["url"])] == (
            int(row["tier"]), weights[row["tier"]], row["license_status"], row["language"], int(row["active"]),
        )
    assert sum(values[4] for values in stored.values()) == 36


def test_csv_and_code_source_definitions_do_not_drift():
    csv_keys = {(row["name"], row["url"]) for row in read_csv_rows()}
    code_keys = {(source["name"], source["url"]) for source in _engine.get_builtin_source_records()}
    assert csv_keys == code_keys


def test_csv_sync_is_idempotent(tmp_path):
    database = tmp_path / "registry.sqlite3"
    source_registry.sync_sources_from_csv(target_path=database)
    source_registry.sync_sources_from_csv(target_path=database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 39


def test_csv_active_flag_controls_ingestion(tmp_path):
    rows = read_csv_rows()
    disabled = next(row for row in rows if row["name"] == "Simple Flying")
    disabled["active"] = "0"
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
    assert not active_names & {"Reuters Aviation", "Financial Times Aviation", "Bloomberg Aviation"}


def test_paid_source_cannot_be_activated_through_the_csv(tmp_path):
    rows = read_csv_rows()
    paid = next(row for row in rows if row["name"] == "Reuters Aviation")
    paid["active"] = "1"
    csv_path = tmp_path / "sources.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=source_registry.SOURCES_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="paid sources cannot be active"):
        source_registry.sync_sources_from_csv(csv_path, tmp_path / "registry.sqlite3")
