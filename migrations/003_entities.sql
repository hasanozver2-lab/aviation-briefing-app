-- Every entity has a permanent, meaningless entity_id ("carrier:000123"). IATA/ICAO codes
-- and names are attributes that may change over time (see entity_history).
CREATE TABLE IF NOT EXISTS groups (
    entity_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    region TEXT NOT NULL,
    tier INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 4),
    metric_approx REAL NOT NULL,
    needs_verification INTEGER NOT NULL DEFAULT 0 CHECK (needs_verification IN (0, 1)),
    tier_override INTEGER CHECK (tier_override BETWEEN 1 AND 4),
    override_reason TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS carriers (
    entity_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    parent_entity_id TEXT REFERENCES groups(entity_id),
    iata TEXT NOT NULL DEFAULT '',
    icao TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    region TEXT NOT NULL,
    alliance TEXT NOT NULL DEFAULT '',
    operator_type TEXT NOT NULL CHECK (operator_type IN ('passenger', 'cargo', 'mixed')),
    tier INTEGER CHECK (tier BETWEEN 1 AND 4),             -- passenger tier; NULL for cargo operators
    cargo_tier INTEGER CHECK (cargo_tier BETWEEN 1 AND 4), -- cargo operators only
    metric_approx REAL NOT NULL,
    fleet_widebody INTEGER NOT NULL DEFAULT 0,
    fleet_narrowbody INTEGER NOT NULL DEFAULT 0,
    fleet_regional INTEGER NOT NULL DEFAULT 0,
    capacity_purchase INTEGER NOT NULL DEFAULT 0 CHECK (capacity_purchase IN (0, 1)),
    needs_verification INTEGER NOT NULL DEFAULT 0 CHECK (needs_verification IN (0, 1)),
    tier_override INTEGER CHECK (tier_override BETWEEN 1 AND 4),
    override_reason TEXT NOT NULL DEFAULT '',
    verification_source TEXT NOT NULL DEFAULT '',
    verified_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS airports (
    entity_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    iata TEXT NOT NULL DEFAULT '',
    icao TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    city TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    is_hub INTEGER NOT NULL DEFAULT 0 CHECK (is_hub IN (0, 1)),
    tier INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 4),
    metric_approx REAL NOT NULL,
    needs_verification INTEGER NOT NULL DEFAULT 0 CHECK (needs_verification IN (0, 1)),
    tier_override INTEGER CHECK (tier_override BETWEEN 1 AND 4),
    override_reason TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS aircraft_types (
    entity_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    code TEXT NOT NULL,
    family TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]'
);

-- Superseded or time-bounded codes and names. Current values live on the entity row.
CREATE TABLE IF NOT EXISTS entity_history (
    entity_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('iata', 'icao', 'name', 'alias')),
    value TEXT NOT NULL,
    valid_from TEXT,
    valid_to TEXT,
    needs_verification INTEGER NOT NULL DEFAULT 0 CHECK (needs_verification IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_carriers_iata ON carriers(iata);
CREATE INDEX IF NOT EXISTS idx_airports_iata ON airports(iata);
CREATE INDEX IF NOT EXISTS idx_entity_history_entity ON entity_history(entity_id);
