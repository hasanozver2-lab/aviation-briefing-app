"""The source catalog: config/sources.csv with its governance columns, and the expansion list merged into it.

config/sources.csv stays the one list of sources. The columns added for the expansion are
source_type, official, mode, timeout_s, status, reason and commercial_use_risk.
"""

import csv
import json
import re
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
SOURCES_CSV_PATH = BASE_DIR / "config" / "sources.csv"
SOURCE_TYPES_PATH = BASE_DIR / "config" / "source_types.json"
EXPANSION_PATH = BASE_DIR / "config" / "source_expansion.json"

BASE_COLUMNS = ("name", "url", "feed_url", "feed_type", "region", "tier", "license_status", "language", "active", "notes")
CATALOG_COLUMNS = ("source_type", "official", "mode", "timeout_s", "status", "reason", "commercial_use_risk")
ALL_COLUMNS = BASE_COLUMNS + CATALOG_COLUMNS
STATUS_ACTIVE = "active"
DEFAULT_TIMEOUT_SECONDS = 3
FEED_TIMEOUT_SECONDS = 10      # RSS/Atom rows keep the 10 s the pipeline always used; the 3 s default is for HTML pages

# Second-level public suffixes (so ana.co.jp and jal.co.jp are two publishers, not one 'co.jp').
TWO_LEVEL_SUFFIXES = {"co.uk", "org.uk", "com.au", "co.jp", "com.tr", "org.tr", "gov.tr", "gov.cn", "gov.in", "com.cn", "com.hk"}


def load_source_types():
    return json.loads(SOURCE_TYPES_PATH.read_text(encoding="utf-8"))


def source_slug(name):
    """Stable source id used as the key in config/feeds_discovered.json."""
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def registrable_key(url):
    """The key that decides whether two URLs belong to the same publisher: the registrable domain. Hosts shared by many
    unrelated agencies are told apart by path (gov.uk: the whole path, gov.br: the first segment) or by host (europa.eu)."""
    parsed = urlparse(url if "//" in str(url) else f"//{url}")
    host = (parsed.hostname or "").lower()
    labels = host.split(".")
    if len(labels) < 2:
        return host
    last_two = ".".join(labels[-2:])
    if last_two == "europa.eu":
        return host
    path_parts = [part for part in parsed.path.split("/") if part]
    if last_two == "gov.uk":
        return "gov.uk/" + "/".join(path_parts)
    if last_two == "gov.br":
        return "gov.br/" + (path_parts[0] if path_parts else "")
    if last_two in TWO_LEVEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return last_two


def row_key(row):
    """Catalog identity of a row: the SEC company for EDGAR rows, otherwise the publisher's registrable domain."""
    notes = notes_of(row)
    if notes.get("cik"):
        return f"sec/{notes['cik']}"
    return notes.get("catalog_key") or registrable_key(row["url"])


def read_rows(path=None):
    with Path(path or SOURCES_CSV_PATH).open(encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def write_rows(rows, path=None):
    with Path(path or SOURCES_CSV_PATH).open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=ALL_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in ALL_COLUMNS})


def notes_of(row):
    try:
        return json.loads(row.get("notes") or "{}")
    except json.JSONDecodeError:
        return {}


def tier_for(source_type, types=None):
    return (types or load_source_types())["types"][source_type]["tier"]


def legacy_defaults(row, types):
    """Catalog columns for a row that predates them, derived from its notes."""
    notes = notes_of(row)
    source_type = types["legacy_type_map"].get(notes.get("source_type"), "trade")
    is_rss = row.get("feed_type") == "rss"
    return {
        "source_type": source_type,
        "official": "true" if notes.get("official") else "false",
        "mode": "full",
        "timeout_s": str(FEED_TIMEOUT_SECONDS if is_rss else DEFAULT_TIMEOUT_SECONDS),
        "status": STATUS_ACTIVE if row.get("active") == "1" else "no_extractable_feed",
        "reason": "" if row.get("active") == "1" else "not probed yet",
        "commercial_use_risk": "",
    }


def new_row(entry, types):
    type_config = types["types"][entry["source_type"]]
    primary = entry["urls"][0]
    notes = {
        "category_hint": "European and other global airlines", "official": type_config["official"], "source_type": entry["source_type"],
        "discovery_urls": entry["urls"],
    }
    for key in ("airline", "airline_code", "cik", "edgar_items", "aviation_filter", "discovery_urls", "catalog_key"):
        if key in entry:
            notes[key] = entry[key]
    is_sec = bool(entry.get("cik"))
    return {
        "name": entry["name"], "url": primary, "feed_url": "", "feed_type": "rss", "region": entry["region"],
        "tier": str(entry.get("tier") or type_config["tier"]), "license_status": "public", "language": entry["language"], "active": "0",
        "notes": json.dumps(notes, ensure_ascii=False, sort_keys=True),
        "source_type": entry["source_type"], "official": "true" if type_config["official"] else "false", "mode": entry["mode"],
        "timeout_s": str(entry.get("timeout_s") or (FEED_TIMEOUT_SECONDS if is_sec else DEFAULT_TIMEOUT_SECONDS)),
        "status": "no_extractable_feed", "reason": "not probed yet", "commercial_use_risk": "",
    }


def merge_expansion(rows, expansion, types=None):
    """Add the expansion sources to the catalog rows. Returns (rows, report).

    A source whose registrable domain already has a row updates that row (type, mode, language, discovery urls) and
    never opens a second one; two entries on the same domain share one row, the extra URL becoming a discovery candidate.
    """
    types = types or load_source_types()
    rows = [dict(row) for row in rows]
    for row in rows:
        defaults = legacy_defaults(row, types)
        for column in CATALOG_COLUMNS:
            row.setdefault(column, "")
            if not row[column]:
                row[column] = defaults[column]
    by_key = {}
    for row in rows:
        by_key.setdefault(row_key(row), row)
    report = {"updated": [], "added": [], "merged_same_domain": []}
    for entry in expansion["sources"]:
        is_sec = bool(entry.get("cik"))
        key = f"sec/{entry['cik']}" if is_sec else entry.get("catalog_key") or registrable_key(entry["urls"][0])
        row = by_key.get(key)
        if row is None:
            row = new_row(entry, types)
            rows.append(row)
            by_key[key] = row
            report["added"].append(entry["name"])
            continue
        notes = notes_of(row)
        urls = list(dict.fromkeys(notes.get("discovery_urls", []) + entry["urls"]))
        notes["discovery_urls"] = urls
        for extra_key in ("aviation_filter", "airline", "airline_code"):
            if extra_key in entry:
                notes.setdefault(extra_key, entry[extra_key])
        notes["source_type_catalog"] = entry["source_type"]
        row["notes"] = json.dumps(notes, ensure_ascii=False, sort_keys=True)
        row["source_type"] = entry["source_type"]
        row["mode"] = entry["mode"]
        if row.get("license_status") == "paid":
            row["license_status"] = "public"      # only the publisher's public feed is used, never a licensed API
        row["official"] = "true" if types["types"][entry["source_type"]]["official"] else "false"
        if entry.get("timeout_s"):
            row["timeout_s"] = str(entry["timeout_s"])
        if row["name"] != entry["name"]:
            report["merged_same_domain"].append(f"{entry['name']} -> {row['name']}")
        else:
            report["updated"].append(entry["name"])
    for sec_row in rows:
        notes = notes_of(sec_row)
        if notes.get("cik"):
            sec_row["tier"] = str(tier_for("exchange", types))
    return rows, report
