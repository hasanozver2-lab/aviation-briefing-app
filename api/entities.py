"""Carrier / group / airport / aircraft entity matching and deterministic section assignment.

The CSV files under config/entities are the source of truth; SQLite is rebuilt from them
at the start of every pipeline run. Every entity has a permanent, meaningless entity_id
("carrier:000123", first CSV column). IATA/ICAO codes and names are attributes that may
change; superseded values live in entity_history.csv.
"""

import csv
import json
import re
import sqlite3
from pathlib import Path

try:
    from . import text_match
except ImportError:
    import text_match


BASE_DIR = Path(__file__).resolve().parent.parent
ENTITY_DIR = BASE_DIR / "config" / "entities"
SECTIONS_CONFIG_PATH = BASE_DIR / "config" / "sections.json"
TIERS_CONFIG_PATH = BASE_DIR / "config" / "entity_tiers.json"
EXCLUSIONS_PATH = ENTITY_DIR / "match_exclusions.json"
MIGRATION_PATH = BASE_DIR / "migrations" / "003_entities.sql"

ALIAS_SEPARATOR = "|"
ENTITY_FILES = {
    "groups": "groups.csv",
    "carriers": "carriers.csv",
    "airports": "airports.csv",
    "aircraft_types": "aircraft_types.csv",
}
ENTITY_PREFIX = {"groups": "group", "carriers": "carrier", "airports": "airport", "aircraft_types": "aircraft"}
HISTORY_FILE = "entity_history.csv"
HISTORY_KINDS = ("iata", "icao", "name", "alias")
HISTORY_ALIAS_KINDS = ("name", "alias")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

COLUMNS = {
    "groups": (
        "entity_id", "slug", "name", "aliases", "region", "tier", "metric_approx", "needs_verification",
        "tier_override", "override_reason",
    ),
    "carriers": (
        "entity_id", "slug", "parent_entity_id", "iata", "icao", "name", "aliases", "region", "alliance",
        "operator_type", "tier", "cargo_tier", "metric_approx", "fleet_widebody", "fleet_narrowbody",
        "fleet_regional", "capacity_purchase", "needs_verification", "tier_override", "override_reason",
        "verification_source", "verified_at",
    ),
    "airports": (
        "entity_id", "slug", "iata", "icao", "name", "city", "country", "aliases", "is_hub", "tier",
        "metric_approx", "needs_verification", "tier_override", "override_reason",
    ),
    "aircraft_types": ("entity_id", "slug", "code", "family", "manufacturer", "aliases"),
}
HISTORY_COLUMNS = ("entity_id", "kind", "value", "valid_from", "valid_to", "needs_verification")

# Two-letter airline designators ("BA", "AA") and airport codes ("IST") are ordinary text
# otherwise (Boeing's ticker is BA), so they only count in an operational context.
FLIGHT_CONTEXT_WORDS = r"(?:flights?|service|services|pilots?|crew|cabin crew|aircraft|jets?|planes?|passengers?)"
NOT_A_YEAR = r"(?!(?:19|20)\d\d(?!\d))"
ROUTE_SEPARATORS = "-–—/→>"
CARRIER_CODE_LENGTH = 2


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_sections_config(path=None):
    return _load_json(path or SECTIONS_CONFIG_PATH)


def load_tiers_config(path=None):
    return _load_json(path or TIERS_CONFIG_PATH)


# --- tier derivation ---------------------------------------------------------

def weighted_fleet(widebody, narrowbody, regional, tiers_config=None, cargo=False):
    """Passenger formula: regional x0.5. Cargo formula: same, regional feeders x0.25."""
    tiers = tiers_config or load_tiers_config()
    weights = tiers["fleet_weights"]
    regional_weight = tiers["cargo_regional_weight"] if cargo else weights["regional"]
    return widebody * weights["widebody"] + narrowbody * weights["narrowbody"] + regional * regional_weight


def tier_for_value(value, minimums):
    """minimums = descending thresholds for tiers 1, 2, 3; anything below is tier 4."""
    for tier, minimum in enumerate(minimums, start=1):
        if value >= minimum:
            return tier
    return len(minimums) + 1


def carrier_tier(weighted_value, tiers_config=None):
    return tier_for_value(weighted_value, (tiers_config or load_tiers_config())["carrier_tier_minimums"])


def group_tier(weighted_value, tiers_config=None):
    return tier_for_value(weighted_value, (tiers_config or load_tiers_config())["group_tier_minimums"])


def airport_tier(passengers_millions, tiers_config=None):
    return tier_for_value(passengers_millions, (tiers_config or load_tiers_config())["airport_tier_minimums_millions"])


def carrier_tiers(fleet, operator_type, capacity_purchase, tiers_config=None):
    """Return (metric, passenger_tier, cargo_tier); the unused tier is None.

    Cargo operators leave the passenger tier. Capacity-purchase regionals cannot rank above
    capacity_purchase_best_tier however large their feeder fleet is.
    """
    tiers = tiers_config or load_tiers_config()
    is_cargo = operator_type == "cargo"
    metric = weighted_fleet(fleet["widebody"], fleet["narrowbody"], fleet["regional"], tiers, cargo=is_cargo)
    tier = carrier_tier(metric, tiers)
    if is_cargo:
        return metric, None, tier
    if capacity_purchase:
        tier = max(tier, tiers["capacity_purchase_best_tier"])
    return metric, tier, None


def format_metric(value):
    return f"{value:g}"


# --- CSV reading and validation ---------------------------------------------

def _read_raw(path, columns):
    with Path(path).open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        header = list(reader.fieldnames or [])
        if header[:1] != ["entity_id"]:
            raise ValueError(f"{Path(path).name}: entity_id must be the first column")
        missing = [column for column in columns if column not in header]
        if missing:
            raise ValueError(f"{Path(path).name}: missing columns {missing}")
        return header, [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def _check_identity(kind, path, rows):
    """entity_id must be well-formed and unique; slug (the permanent human key) unique."""
    id_pattern = re.compile(rf"^{ENTITY_PREFIX[kind]}:\d{{6}}$")
    seen_ids, seen_slugs = set(), set()
    name = Path(path).name
    for row in rows:
        entity_id, slug = row["entity_id"], row["slug"]
        if not id_pattern.match(entity_id):
            raise ValueError(f"{name}: invalid entity_id {entity_id!r} (expected {ENTITY_PREFIX[kind]}:NNNNNN)")
        if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug):
            raise ValueError(f"{name}: invalid slug {slug!r} for {entity_id}")
        if entity_id in seen_ids:
            raise ValueError(f"{name}: duplicate entity_id {entity_id}")
        if slug in seen_slugs:
            raise ValueError(f"{name}: duplicate slug {slug}")
        seen_ids.add(entity_id)
        seen_slugs.add(slug)


def _check_unique_code(path, rows, column):
    seen = set()
    for row in rows:
        value = row[column]
        if value and value in seen:
            raise ValueError(f"{Path(path).name}: duplicate {column} {value}")
        if value:
            seen.add(value)


def _aliases(row):
    return [alias.strip() for alias in row["aliases"].split(ALIAS_SEPARATOR) if alias.strip()]


def _flag(row, column, path):
    value = row[column] or "0"
    if value not in {"0", "1"}:
        raise ValueError(f"{Path(path).name}: {column} must be 0 or 1 for {row['entity_id']}")
    return int(value)


def _number(row, column, path, kind=float):
    try:
        return kind(row[column])
    except ValueError as exc:
        raise ValueError(f"{Path(path).name}: {column} is not a number for {row['entity_id']}") from exc


def _tier_override(row, path):
    """A hand-set tier needs a written reason; returns the override or None."""
    value = row["tier_override"]
    if not value:
        return None
    name = Path(path).name
    if not row["override_reason"]:
        raise ValueError(f"{name}: {row['entity_id']} sets tier_override without override_reason")
    try:
        tier = int(value)
    except ValueError:
        tier = 0
    if not 1 <= tier <= 4:
        raise ValueError(f"{name}: tier_override must be 1-4 for {row['entity_id']}")
    return tier


def _check_derived(path, row, expected_metric, expected_tier, tiers_config, tier_column="tier"):
    """The CSV states derived values; they must match what the inputs (and any override) produce."""
    stated_metric = _number(row, "metric_approx", path)
    expected_text = "" if expected_tier is None else str(expected_tier)
    wrong = abs(stated_metric - expected_metric) > tiers_config["metric_tolerance"] or row[tier_column] != expected_text
    if wrong:
        raise ValueError(
            f"{Path(path).name}: {row['entity_id']} states metric_approx={row['metric_approx']} "
            f"{tier_column}={row[tier_column]!r} but its inputs give {format_metric(expected_metric)} / "
            f"{tier_column} {expected_text!r}. Run: python -m scripts.recompute_entity_tiers"
        )


def load_carriers(path=None, sections_config=None, tiers_config=None, group_ids=None):
    path = Path(path or ENTITY_DIR / ENTITY_FILES["carriers"])
    regions = set((sections_config or load_sections_config())["regions"])
    tiers = tiers_config or load_tiers_config()
    _, rows = _read_raw(path, COLUMNS["carriers"])
    _check_identity("carriers", path, rows)
    _check_unique_code(path, rows, "iata")
    carriers = []
    for row in rows:
        if row["region"] not in regions:
            raise ValueError(f"{path.name}: unknown region {row['region']!r} for {row['entity_id']}")
        if row["operator_type"] not in tiers["operator_types"]:
            raise ValueError(f"{path.name}: invalid operator_type {row['operator_type']!r} for {row['entity_id']}")
        parent = row["parent_entity_id"]
        if parent and group_ids is not None and parent not in group_ids:
            raise ValueError(f"{path.name}: {row['entity_id']} has unknown parent_entity_id {parent}")
        fleet = {
            kind: _number(row, f"fleet_{kind}", path, int)
            for kind in ("widebody", "narrowbody", "regional")
        }
        if any(count < 0 for count in fleet.values()):
            raise ValueError(f"{path.name}: negative fleet for {row['entity_id']}")
        capacity_purchase = _flag(row, "capacity_purchase", path)
        override = _tier_override(row, path)
        metric, tier, cargo_tier = carrier_tiers(fleet, row["operator_type"], capacity_purchase, tiers)
        if override is not None and tier is not None:
            tier = override
        if override is not None and cargo_tier is not None:
            cargo_tier = override
        _check_derived(path, row, metric, tier, tiers, "tier")
        _check_derived(path, row, metric, cargo_tier, tiers, "cargo_tier")
        carriers.append({
            "entity_id": row["entity_id"], "slug": row["slug"], "parent_entity_id": parent, "iata": row["iata"],
            "icao": row["icao"], "name": row["name"], "aliases": _aliases(row), "region": row["region"],
            "alliance": row["alliance"], "operator_type": row["operator_type"], "tier": tier,
            "cargo_tier": cargo_tier, "metric_approx": metric,
            **{f"fleet_{kind}": count for kind, count in fleet.items()},
            "capacity_purchase": capacity_purchase, "needs_verification": _flag(row, "needs_verification", path),
            "tier_override": override, "override_reason": row["override_reason"],
            "verification_source": row["verification_source"], "verified_at": row["verified_at"],
        })
    return carriers


def load_groups(path=None, carriers=None, sections_config=None, tiers_config=None):
    """A group's tier comes from the sum of its non-cargo brands against the group thresholds."""
    path = Path(path or ENTITY_DIR / ENTITY_FILES["groups"])
    regions = set((sections_config or load_sections_config())["regions"])
    tiers = tiers_config or load_tiers_config()
    _, rows = _read_raw(path, COLUMNS["groups"])
    _check_identity("groups", path, rows)
    groups = []
    for row in rows:
        if row["region"] not in regions:
            raise ValueError(f"{path.name}: unknown region {row['region']!r} for {row['entity_id']}")
        override = _tier_override(row, path)
        if carriers is not None:
            members = [c for c in carriers if c["parent_entity_id"] == row["entity_id"] and c["operator_type"] != "cargo"]
            if not members:
                raise ValueError(f"{path.name}: group {row['entity_id']} has no member brands")
            metric = sum(member["metric_approx"] for member in members)
            _check_derived(path, row, metric, override or group_tier(metric, tiers), tiers)
        groups.append({
            "entity_id": row["entity_id"], "slug": row["slug"], "name": row["name"], "aliases": _aliases(row),
            "region": row["region"], "tier": int(row["tier"]), "metric_approx": float(row["metric_approx"]),
            "needs_verification": _flag(row, "needs_verification", path),
            "tier_override": override, "override_reason": row["override_reason"],
        })
    return groups


def load_airports(path=None, sections_config=None, tiers_config=None):
    path = Path(path or ENTITY_DIR / ENTITY_FILES["airports"])
    country_regions = (sections_config or load_sections_config())["country_regions"]
    tiers = tiers_config or load_tiers_config()
    _, rows = _read_raw(path, COLUMNS["airports"])
    _check_identity("airports", path, rows)
    _check_unique_code(path, rows, "iata")
    airports = []
    for row in rows:
        if row["country"] not in country_regions:
            raise ValueError(f"{path.name}: country {row['country']!r} of {row['entity_id']} has no region in sections.json")
        passengers = _number(row, "metric_approx", path)
        override = _tier_override(row, path)
        tier = override or airport_tier(passengers, tiers)
        _check_derived(path, row, passengers, tier, tiers)
        is_hub = _flag(row, "is_hub", path)
        if tier <= tiers["hub_airport_max_tier"] and not is_hub:
            raise ValueError(
                f"{path.name}: {row['entity_id']} is tier {tier} so it must be is_hub=1. "
                "Run: python -m scripts.recompute_entity_tiers"
            )
        airports.append({
            "entity_id": row["entity_id"], "slug": row["slug"], "iata": row["iata"], "icao": row["icao"],
            "name": row["name"], "city": row["city"], "country": row["country"], "aliases": _aliases(row),
            "is_hub": is_hub, "tier": tier, "metric_approx": passengers,
            "needs_verification": _flag(row, "needs_verification", path),
            "tier_override": override, "override_reason": row["override_reason"],
        })
    return airports


def load_aircraft_types(path=None):
    path = Path(path or ENTITY_DIR / ENTITY_FILES["aircraft_types"])
    _, rows = _read_raw(path, COLUMNS["aircraft_types"])
    _check_identity("aircraft_types", path, rows)
    return [
        {"entity_id": row["entity_id"], "slug": row["slug"], "code": row["code"], "family": row["family"],
         "manufacturer": row["manufacturer"], "aliases": _aliases(row)}
        for row in rows
    ]


def load_history(path=None, known_entity_ids=None):
    path = Path(path or ENTITY_DIR / HISTORY_FILE)
    _, rows = _read_raw(path, HISTORY_COLUMNS)
    history = []
    for row in rows:
        label = f"{path.name}: {row['entity_id']} {row['kind']} {row['value']!r}"
        if known_entity_ids is not None and row["entity_id"] not in known_entity_ids:
            raise ValueError(f"{label}: unknown entity_id")
        if row["kind"] not in HISTORY_KINDS:
            raise ValueError(f"{label}: invalid kind")
        for column in ("valid_from", "valid_to"):
            if row[column] and not ISO_DATE.match(row[column]):
                raise ValueError(f"{label}: {column} must be YYYY-MM-DD")
        if row["valid_from"] and row["valid_to"] and row["valid_from"] > row["valid_to"]:
            raise ValueError(f"{label}: valid_from is after valid_to")
        history.append({
            "entity_id": row["entity_id"], "kind": row["kind"], "value": row["value"],
            "valid_from": row["valid_from"] or None, "valid_to": row["valid_to"] or None,
            "needs_verification": _flag(row, "needs_verification", path),
        })
    return history


def load_all(directory=None, sections_config=None, tiers_config=None):
    directory = Path(directory or ENTITY_DIR)
    sections = sections_config or load_sections_config()
    tiers = tiers_config or load_tiers_config()
    raw_groups = _read_raw(directory / ENTITY_FILES["groups"], COLUMNS["groups"])[1]
    group_ids = {row["entity_id"] for row in raw_groups}
    carriers = load_carriers(directory / ENTITY_FILES["carriers"], sections, tiers, group_ids)
    groups = load_groups(directory / ENTITY_FILES["groups"], carriers, sections, tiers)
    airports = load_airports(directory / ENTITY_FILES["airports"], sections, tiers)
    aircraft = load_aircraft_types(directory / ENTITY_FILES["aircraft_types"])
    known_ids = {item["entity_id"] for collection in (groups, carriers, airports, aircraft) for item in collection}
    history = load_history(directory / HISTORY_FILE, known_ids)
    return {"groups": groups, "carriers": carriers, "airports": airports, "aircraft_types": aircraft, "history": history}


def recompute_derived_columns(directory=None, tiers_config=None):
    """Rewrite metric_approx, tier, cargo_tier and tier-1/2 hub flags in the CSVs from their raw inputs."""
    directory = Path(directory or ENTITY_DIR)
    tiers = tiers_config or load_tiers_config()
    sources = {name: _read_raw(directory / ENTITY_FILES[name], COLUMNS[name]) for name in ("carriers", "groups", "airports")}

    def final(row, computed):
        return str(int(row["tier_override"]) if row["tier_override"] else computed)

    member_metric = {}
    for row in sources["carriers"][1]:
        fleet = {kind: int(row[f"fleet_{kind}"]) for kind in ("widebody", "narrowbody", "regional")}
        metric, tier, cargo_tier = carrier_tiers(fleet, row["operator_type"], row["capacity_purchase"] == "1", tiers)
        row["metric_approx"] = format_metric(metric)
        row["tier"] = "" if tier is None else final(row, tier)
        row["cargo_tier"] = "" if cargo_tier is None else final(row, cargo_tier)
        if row["parent_entity_id"] and row["operator_type"] != "cargo":
            member_metric[row["parent_entity_id"]] = member_metric.get(row["parent_entity_id"], 0) + metric
    for row in sources["groups"][1]:
        metric = member_metric.get(row["entity_id"], 0)
        row["metric_approx"], row["tier"] = format_metric(metric), final(row, group_tier(metric, tiers))
    for row in sources["airports"][1]:
        row["tier"] = final(row, airport_tier(float(row["metric_approx"]), tiers))
        if int(row["tier"]) <= tiers["hub_airport_max_tier"]:
            row["is_hub"] = "1"

    for name, (header, rows) in sources.items():
        with (directory / ENTITY_FILES[name]).open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)
    return {name: len(rows) for name, (_, rows) in sources.items()}


# --- SQLite -------------------------------------------------------------------

def _dump_aliases(aliases):
    return json.dumps(aliases, ensure_ascii=False)


def sync_entities(database, directory=None, sections_config=None):
    """Rebuild the entity tables from the CSV files; safe to run on every pipeline start."""
    data = load_all(directory, sections_config)
    target = Path(database)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        for table in ("entity_history", "carriers", "groups", "airports", "aircraft_types"):
            connection.execute(f"DELETE FROM {table}")
        connection.executemany(
            "INSERT INTO groups (entity_id, slug, name, aliases_json, region, tier, metric_approx, needs_verification,"
            " tier_override, override_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(g["entity_id"], g["slug"], g["name"], _dump_aliases(g["aliases"]), g["region"], g["tier"],
              g["metric_approx"], g["needs_verification"], g["tier_override"], g["override_reason"])
             for g in data["groups"]],
        )
        connection.executemany(
            "INSERT INTO carriers (entity_id, slug, parent_entity_id, iata, icao, name, aliases_json, region, alliance,"
            " operator_type, tier, cargo_tier, metric_approx, fleet_widebody, fleet_narrowbody, fleet_regional,"
            " capacity_purchase, needs_verification, tier_override, override_reason, verification_source, verified_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(c["entity_id"], c["slug"], c["parent_entity_id"] or None, c["iata"], c["icao"], c["name"],
              _dump_aliases(c["aliases"]), c["region"], c["alliance"], c["operator_type"], c["tier"],
              c["cargo_tier"], c["metric_approx"], c["fleet_widebody"], c["fleet_narrowbody"], c["fleet_regional"],
              c["capacity_purchase"], c["needs_verification"], c["tier_override"], c["override_reason"],
              c["verification_source"], c["verified_at"]) for c in data["carriers"]],
        )
        connection.executemany(
            "INSERT INTO airports (entity_id, slug, iata, icao, name, city, country, aliases_json, is_hub, tier,"
            " metric_approx, needs_verification, tier_override, override_reason)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(a["entity_id"], a["slug"], a["iata"], a["icao"], a["name"], a["city"], a["country"],
              _dump_aliases(a["aliases"]), a["is_hub"], a["tier"], a["metric_approx"], a["needs_verification"],
              a["tier_override"], a["override_reason"]) for a in data["airports"]],
        )
        connection.executemany(
            "INSERT INTO aircraft_types VALUES (?, ?, ?, ?, ?, ?)",
            [(t["entity_id"], t["slug"], t["code"], t["family"], t["manufacturer"], _dump_aliases(t["aliases"]))
             for t in data["aircraft_types"]],
        )
        connection.executemany(
            "INSERT INTO entity_history VALUES (?, ?, ?, ?, ?, ?)",
            [(h["entity_id"], h["kind"], h["value"], h["valid_from"], h["valid_to"], h["needs_verification"])
             for h in data["history"]],
        )
    return {**{name: len(data[name]) for name in ENTITY_FILES}, "history": len(data["history"])}


# --- matching -----------------------------------------------------------------

def _carrier_code_patterns(code):
    escaped = re.escape(code)
    return [
        re.compile(rf"(?<!\w){escaped}\s?{NOT_A_YEAR}\d{{1,4}}(?!\w)"),
        re.compile(rf"(?<!\w){escaped}(?:'s)?\s+{FLIGHT_CONTEXT_WORDS}(?!\w)"),
        re.compile(rf"(?<!\w){escaped}'s(?!\w)"),
    ]


def _airport_code_patterns(code):
    escaped = re.escape(code)
    separators = re.escape(ROUTE_SEPARATORS)
    return [
        re.compile(rf"\({escaped}\)"),
        re.compile(rf"(?<![\w]){escaped}\s?[{separators}]\s?[A-Z]{{3}}(?!\w)"),
        re.compile(rf"(?<![\w])[A-Z]{{3}}\s?[{separators}]\s?{escaped}(?!\w)"),
        re.compile(rf"(?<!\w){escaped}\s+[Aa]irport(?!\w)"),
        re.compile(rf"(?<!\w){escaped}\s+\d{{1,3}}(?:[.,]\d{{3}})+(?!\w)"),
    ]


class _Entity:
    """One matchable thing: alias term set plus optional context-only code patterns."""

    def __init__(self, payload, alias_terms, code_patterns=()):
        self.payload = payload
        self.entity_id = payload["entity_id"]
        self.terms = text_match.TermSet(alias_terms)
        self.code_patterns = list(code_patterns)

    def spans(self, prepared):
        found = [(start, end) for _, start, end in self.terms.spans(prepared)]
        for pattern in self.code_patterns:
            found.extend(match.span() for match in pattern.finditer(prepared.raw))
        return found


def _is_inside(span, containers, strictly_longer):
    start, end = span
    for container_start, container_end in containers:
        if container_start <= start and end <= container_end:
            if not strictly_longer or (container_end - container_start) > (end - start):
                return True
    return False


def _reject_alias_collisions(entities, label):
    owners = {}
    for entity in entities:
        for term in entity.terms.terms:
            key = text_match.fold(term.lstrip(text_match.CASE_SENSITIVE_MARK).rstrip(text_match.STEM_MARK))
            if owners.setdefault(key, entity.entity_id) != entity.entity_id:
                raise ValueError(f"{label}: alias {term!r} is shared by {owners[key]} and {entity.entity_id}")


def empty_entities():
    return {"groups": [], "carriers": [], "airports": [], "aircraft": []}


class EntityIndex:
    def __init__(self, data, sections_config=None, exclusion_phrases=None):
        self.config = sections_config or load_sections_config()
        self.country_regions = self.config["country_regions"]
        history_aliases = {}
        for row in data.get("history", []):
            if row["kind"] in HISTORY_ALIAS_KINDS:
                history_aliases.setdefault(row["entity_id"], []).append(row["value"])

        def aliases_of(item):
            return [item["name"], *item["aliases"], *history_aliases.get(item["entity_id"], [])]

        self.groups = [_Entity(g, aliases_of(g)) for g in data["groups"]]
        self.carriers = [
            _Entity(c, aliases_of(c), _carrier_code_patterns(c["iata"]) if len(c["iata"]) == CARRIER_CODE_LENGTH else [])
            for c in data["carriers"]
        ]
        self.airports = [
            _Entity(a, aliases_of(a), _airport_code_patterns(a["iata"]) if a["iata"] else [])
            for a in data["airports"]
        ]
        self.aircraft = [
            _Entity(t, [t["code"], *t["aliases"], *history_aliases.get(t["entity_id"], [])])
            for t in data["aircraft_types"]
        ]
        for label, entities in (("groups", self.groups), ("carriers", self.carriers),
                                ("airports", self.airports), ("aircraft_types", self.aircraft)):
            _reject_alias_collisions(entities, label)
        manufacturers = sorted({t["manufacturer"] for t in data["aircraft_types"] if t["manufacturer"]})
        self.manufacturers = text_match.TermSet(manufacturers)
        self.exclusions = text_match.TermSet(exclusion_phrases or [])
        self.regulator_terms = text_match.TermSet(self.config["regulator_terms"])
        self.supply_chain_terms = text_match.TermSet(self.config["supply_chain_terms"])

    @classmethod
    def from_csv(cls, directory=None, sections_config=None):
        config = sections_config or load_sections_config()
        data = load_all(directory, config)
        phrases = _load_json(EXCLUSIONS_PATH)["phrases"] if EXCLUSIONS_PATH.exists() else []
        return cls(data, config, phrases)

    def _rank(self, entities, fields, outside_rivals=None):
        """Order matches title-first, then by earliest position; drop shadowed matches.

        A match is shadowed when it sits inside a longer alias of another entity
        ("Air France" inside "Air France-KLM") or inside an exclusion phrase
        ("Emirates" inside "United Arab Emirates"). outside_rivals holds, per field, spans of
        another entity kind (a group name such as "Air France-KLM" shadows its brands).
        """
        best = {}
        for field_index, prepared in enumerate(fields):
            exclusion_spans = [(start, end) for _, start, end in self.exclusions.spans(prepared)]
            candidates = {entity.entity_id: (entity, entity.spans(prepared)) for entity in entities}
            candidates = {key: value for key, value in candidates.items() if value[1]}
            for entity_id, (entity, spans) in candidates.items():
                rivals = [
                    span for other_id, (_, other_spans) in candidates.items() if other_id != entity_id
                    for span in other_spans
                ] + list((outside_rivals or [[], []])[field_index])
                surviving = [
                    span for span in spans
                    if not _is_inside(span, exclusion_spans, strictly_longer=False)
                    and not _is_inside(span, rivals, strictly_longer=True)
                ]
                if surviving and entity_id not in best:
                    best[entity_id] = (field_index, min(start for start, _ in surviving), entity)
        return [entity.payload for _, _, entity in sorted(best.values(), key=lambda item: item[:2])]

    def find(self, title, description=""):
        fields = [text_match.prepare(title), text_match.prepare(description)]
        group_spans = [[span for entity in self.groups for span in entity.spans(prepared)] for prepared in fields]
        return {
            "groups": [
                {"entity_id": g["entity_id"], "slug": g["slug"], "name": g["name"], "region": g["region"], "tier": g["tier"]}
                for g in self._rank(self.groups, fields)
            ],
            "carriers": [
                {"entity_id": c["entity_id"], "slug": c["slug"], "iata": c["iata"], "name": c["name"],
                 "region": c["region"], "group_entity_id": c["parent_entity_id"], "tier": c["tier"] or c["cargo_tier"]}
                for c in self._rank(self.carriers, fields, group_spans)
            ],
            "airports": [
                {"entity_id": a["entity_id"], "slug": a["slug"], "iata": a["iata"], "name": a["name"],
                 "country": a["country"], "tier": a["tier"]}
                for a in self._rank(self.airports, fields)
            ],
            "aircraft": [
                {"entity_id": t["entity_id"], "slug": t["slug"], "code": t["code"], "family": t["family"],
                 "manufacturer": t["manufacturer"]}
                for t in self._rank(self.aircraft, fields)
            ],
        }

    def assign_sections(self, entities, event_type, title, description=""):
        """Return (primary_section, secondary_tags).

        Every rule in config.rule_order that fires contributes its section(s); the first
        becomes the primary section and the remaining distinct ones become secondary tags.
        """
        text = text_match.prepare(f"{title or ''}. {description or ''}")
        sections = []
        for rule in self.config["rule_order"]:
            for section in self._rule_sections(rule, entities, event_type, text):
                if section and section not in sections:
                    sections.append(section)
        if not sections:
            return self.config["unassigned_section"], []
        return sections[0], sections[1:]

    def assign_section(self, entities, event_type, title, description=""):
        return self.assign_sections(entities, event_type, title, description)[0]

    def _rule_sections(self, rule, entities, event_type, text):
        config = self.config
        if rule == "event_type":
            return [config["event_type_sections"].get(event_type or "")]
        if rule == "regulator":
            return [config["regulator_section"]] if self.regulator_terms.any(text) else []
        if rule == "carrier_region":
            return [item["region"] for item in (*entities["carriers"], *entities["groups"])]
        if rule == "airport_region":
            return [self.country_regions.get(item["country"]) for item in entities["airports"]]
        if rule == "manufacturer":
            has_supply_signal = entities["aircraft"] or self.manufacturers.any(text) or self.supply_chain_terms.any(text)
            return [config["manufacturer_section"]] if has_supply_signal else []
        raise ValueError(f"unknown section rule: {rule}")


def compact_codes(entities):
    """Token-light form sent to the model: codes (or slugs where no code exists)."""
    return {
        "groups": [item["slug"] for item in entities.get("groups", [])],
        "carriers": [item["iata"] or item["slug"] for item in entities["carriers"]],
        "airports": [item["iata"] or item["slug"] for item in entities["airports"]],
        "aircraft": [item["code"] for item in entities["aircraft"]],
    }


def annotate_articles(articles, index):
    """Attach entities, the primary region section and secondary tags to each article in place."""
    for article in articles:
        title, description = article.get("title", ""), article.get("description", "")
        entities = index.find(title, description)
        primary, secondary = index.assign_sections(entities, article.get("event_type"), title, description)
        article["entities"] = entities
        article["region_section"] = primary
        article["secondary_tags"] = secondary
    return articles
