CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    feed_url TEXT,
    feed_type TEXT NOT NULL,
    region TEXT NOT NULL,
    tier INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 4),
    reliability_weight REAL NOT NULL CHECK (reliability_weight >= 0 AND reliability_weight <= 1),
    license_status TEXT NOT NULL CHECK (license_status IN ('public', 'paid', 'restricted', 'unknown')),
    language TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1)),
    added_at TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE(name, url)
);

CREATE TABLE IF NOT EXISTS source_stats (
    source_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    articles_ingested INTEGER NOT NULL DEFAULT 0 CHECK (articles_ingested >= 0),
    articles_in_clusters INTEGER NOT NULL DEFAULT 0 CHECK (articles_in_clusters >= 0),
    clusters_included_in_brief INTEGER NOT NULL DEFAULT 0 CHECK (clusters_included_in_brief >= 0),
    first_to_report_count INTEGER NOT NULL DEFAULT 0 CHECK (first_to_report_count >= 0),
    PRIMARY KEY (source_id, date),
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sources_active_region_tier
    ON sources(active, region, tier);
CREATE INDEX IF NOT EXISTS idx_source_stats_date
    ON source_stats(date);
