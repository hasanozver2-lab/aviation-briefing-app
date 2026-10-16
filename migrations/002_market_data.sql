CREATE TABLE IF NOT EXISTS market_series (
    series_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    unit TEXT NOT NULL,
    source TEXT NOT NULL,
    frequency TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_observations (
    series_id TEXT NOT NULL,
    date TEXT NOT NULL,
    value REAL NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (series_id, date),
    FOREIGN KEY (series_id) REFERENCES market_series(series_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    event_type TEXT NOT NULL,
    occurred_on TEXT NOT NULL,
    headline TEXT NOT NULL,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    related_market_event_id INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(event_type, occurred_on, headline, source),
    FOREIGN KEY (related_market_event_id) REFERENCES events(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_market_observations_series_date
    ON market_observations(series_id, date);
CREATE INDEX IF NOT EXISTS idx_events_type_date
    ON events(event_type, occurred_on);
