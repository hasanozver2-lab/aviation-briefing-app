"""SQLite-backed governance and measurement for briefing sources."""

import csv
import json
import os
import re
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "source_registry.json"
MIGRATION_PATH = BASE_DIR / "migrations" / "001_source_registry.sql"
DEFAULT_DATABASE_PATH = BASE_DIR / "data" / "source_registry.sqlite3"
SOURCES_CSV_PATH = BASE_DIR / "config" / "sources.csv"
SOURCES_CSV_COLUMNS = (
    "name", "url", "feed_url", "feed_type", "region", "tier",
    "license_status", "language", "active", "notes",
)

TIER_BY_SOURCE_TYPE = {
    "airline_ir": 1,
    "airline_newsroom": 1,
    "official_social": 1,
    "mainstream": 3,
}
TIER_TWO_SOURCES = {"FlightGlobal", "Flightradar24"}
TURKISH_SOURCES = {"HavaHaber", "Tolga Özbek Havacılık"}
REGION_BY_CATEGORY = {
    "Turkey / THY and Turkish aviation": "Turkey",
    "North American airlines": "North America",
    "Asia-Pacific airlines": "Asia-Pacific",
    "Middle East airlines": "Middle East",
    "Latin American airlines": "Latin America",
}
REGION_BY_SOURCE = {
    "Delta News Hub": "North America",
    "Lufthansa Group Newsroom": "Europe",
    "Air France Press Releases": "Europe",
    "KLM Newsroom": "Europe",
    "Ryanair Newsroom": "Europe",
    "easyJet Media Centre": "Europe",
    "Emirates Newsroom": "Middle East",
    "Qatar Airways Official Tumblr": "Middle East",
}
TITLE_TOKEN_PATTERN = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)
TITLE_STOP_WORDS = {
    "about", "after", "airline", "airlines", "announces", "announcement", "from",
    "have", "into", "more", "news", "press", "release", "that", "the", "this",
    "with", "will", "your", "2026", "2025",
}


def database_path(value=None):
    """Resolve the local/volume-backed registry path without writing at runtime."""
    configured_path = value or os.environ.get("SOURCE_REGISTRY_DB_PATH")
    if not configured_path:
        return DEFAULT_DATABASE_PATH
    configured = Path(configured_path)
    return configured if configured.is_absolute() else BASE_DIR / configured


def load_registry_config():
    with CONFIG_PATH.open(encoding="utf-8") as config_file:
        return json.load(config_file)


def reliability_weight_for_tier(tier, config=None):
    registry_config = config or load_registry_config()
    try:
        return float(registry_config["tier_reliability_weights"][str(int(tier))])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Missing reliability weight for tier {tier}") from exc


def infer_region(source):
    if source.get("region"):
        return str(source["region"])
    source_name = source.get("name", "")
    if source_name in REGION_BY_SOURCE:
        return REGION_BY_SOURCE[source_name]
    return REGION_BY_CATEGORY.get(source.get("category_hint"), "Global")


def infer_tier(source):
    if source.get("tier"):
        return int(source["tier"])
    if source.get("name") in TIER_TWO_SOURCES:
        return 2
    return TIER_BY_SOURCE_TYPE.get(source.get("source_type"), 4)


def infer_language(source):
    if source.get("language"):
        return str(source["language"])
    return "tr" if source.get("name") in TURKISH_SOURCES else "en"


def source_to_registry_record(source, config=None):
    """Convert a runtime feed definition into the immutable source governance schema."""
    tier = infer_tier(source)
    source_url = str(source.get("url") or "").strip()
    feed_type = str(source.get("fetch_mode") or "rss")
    notes = {
        key: value
        for key, value in source.items()
        if key not in {"name", "url", "region", "tier", "reliability_weight", "license_status", "language", "active"}
    }
    return {
        "name": str(source.get("name") or "Unknown source"),
        "url": source_url,
        "feed_url": source_url,
        "feed_type": feed_type,
        "region": infer_region(source),
        "tier": tier,
        "reliability_weight": reliability_weight_for_tier(tier, config),
        "license_status": "paid" if source.get("license_required") else "public",
        "language": infer_language(source),
        "active": 1 if source.get("active", True) else 0,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "notes": json.dumps(notes, ensure_ascii=False, sort_keys=True),
    }


UPSERT_SOURCE_SQL = """
    INSERT INTO sources (
        name, url, feed_url, feed_type, region, tier, reliability_weight,
        license_status, language, active, added_at, notes
    ) VALUES (
        :name, :url, :feed_url, :feed_type, :region, :tier, :reliability_weight,
        :license_status, :language, :active, :added_at, :notes
    )
    ON CONFLICT(name, url) DO UPDATE SET
        feed_url = excluded.feed_url,
        feed_type = excluded.feed_type,
        region = excluded.region,
        tier = excluded.tier,
        reliability_weight = excluded.reliability_weight,
        license_status = excluded.license_status,
        language = excluded.language,
        active = excluded.active,
        notes = excluded.notes
"""


def _write_source_records(records, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        for record in records:
            connection.execute(UPSERT_SOURCE_SQL, record)
    return target


def migrate_sources(source_records, target_path=None):
    """Apply the schema and idempotently upsert the currently configured sources."""
    config = load_registry_config()
    records = [source_to_registry_record(source, config) for source in source_records]
    return _write_source_records(records, database_path(target_path))


def load_sources_csv(csv_path=None, config=None):
    """Read config/sources.csv into registry records; invalid rows fail loudly."""
    path = Path(csv_path or SOURCES_CSV_PATH)
    registry_config = config or load_registry_config()
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = [column for column in SOURCES_CSV_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path.name}: missing columns {missing}")
        rows = list(reader)

    added_at = datetime.now(timezone.utc).isoformat()
    records = []
    for line_number, row in enumerate(rows, start=2):
        label = f"{path.name} line {line_number} ({row.get('name')})"
        if row["license_status"] not in registry_config["license_statuses"]:
            raise ValueError(f"{label}: invalid license_status {row['license_status']!r}")
        if row["region"] not in registry_config["regions"]:
            raise ValueError(f"{label}: invalid region {row['region']!r}")
        if row["active"] not in {"0", "1"}:
            raise ValueError(f"{label}: active must be 0 or 1")
        if row["license_status"] == "paid" and row["active"] == "1":
            raise ValueError(f"{label}: paid sources cannot be active without a licence")
        try:
            json.loads(row["notes"] or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label}: notes is not valid JSON") from exc
        tier = int(row["tier"])
        records.append({
            "name": row["name"],
            "url": row["url"],
            "feed_url": row["feed_url"] or None,
            "feed_type": row["feed_type"],
            "region": row["region"],
            "tier": tier,
            "reliability_weight": reliability_weight_for_tier(tier, registry_config),
            "license_status": row["license_status"],
            "language": row["language"],
            "active": int(row["active"]),
            "added_at": added_at,
            "notes": row["notes"] or "{}",
        })
    return records


def sync_sources_from_csv(csv_path=None, target_path=None):
    """Build/refresh the SQLite registry from config/sources.csv (the source of truth)."""
    records = load_sources_csv(csv_path)
    return _write_source_records(records, database_path(target_path))


def export_sources_csv(source_records, csv_path=None):
    """One-off helper: write runtime source definitions as the CSV registry."""
    config = load_registry_config()
    path = Path(csv_path or SOURCES_CSV_PATH)
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=SOURCES_CSV_COLUMNS)
        writer.writeheader()
        for source in source_records:
            record = source_to_registry_record(source, config)
            writer.writerow({column: record[column] for column in SOURCES_CSV_COLUMNS})
    return path


def load_active_sources(source_records, target_path=None):
    """Apply active flags and governance metadata when the packaged registry exists."""
    target = database_path(target_path)
    if not target.is_file():
        return [source for source in source_records if source.get("active", True)]

    try:
        with sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT id, name, url, feed_url, feed_type, region, tier, reliability_weight, license_status, active FROM sources"
            ).fetchall()
    except sqlite3.Error:
        return source_records

    registered = {(row["name"], row["url"]): row for row in rows}
    active_sources = []
    for source in source_records:
        if not source.get("active", True):
            continue
        row = registered.get((source.get("name"), source.get("url")))
        if row is None:
            active_sources.append(source)
            continue
        if not row["active"]:
            continue
        governed_source = dict(source)
        governed_source.update({
            "source_id": row["id"],
            "region": row["region"],
            "tier": row["tier"],
            "reliability_weight": row["reliability_weight"],
            "license_status": row["license_status"],
            "license_required": row["license_status"] == "paid",
        })
        if row["feed_url"]:
            governed_source["url"] = row["feed_url"]
        if row["feed_type"] in {"rss", "atom", "html"}:
            governed_source["fetch_mode"] = "html" if row["feed_type"] == "html" else governed_source.get("fetch_mode", "rss")
        active_sources.append(governed_source)
    return active_sources


def _title_tokens(title):
    return {
        token.casefold()
        for token in TITLE_TOKEN_PATTERN.findall(str(title or ""))
        if token.casefold() not in TITLE_STOP_WORDS
    }


def _similarity(left, right):
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def title_similarity(left_title, right_title):
    """Jaccard similarity of the meaningful title words, 0-1."""
    return _similarity(_title_tokens(left_title), _title_tokens(right_title))


def cluster_articles_for_stats(articles):
    """Create conservative same-event groups only for source-performance measurement."""
    ordered_articles = sorted(
        enumerate(articles),
        key=lambda item: (item[1].get("timestamp", 0), item[1].get("link", "")),
    )
    clusters = []
    for index, article in ordered_articles:
        tokens = _title_tokens(article.get("title"))
        best_cluster = None
        best_similarity = 0.0
        for cluster in clusters:
            similarity = _similarity(tokens, cluster["tokens"])
            if similarity > best_similarity:
                best_cluster = cluster
                best_similarity = similarity
        if best_cluster and best_similarity >= 0.6:
            best_cluster["article_indexes"].append(index)
            best_cluster["tokens"].update(tokens)
            continue
        clusters.append({"tokens": tokens, "article_indexes": [index]})
    return [cluster["article_indexes"] for cluster in clusters]


def _included_story_urls(briefing):
    stories = briefing.get("stories", []) if isinstance(briefing, dict) else []
    return {
        str(story.get("original_source", {}).get("url") or "").rstrip("/")
        for story in stories
        if isinstance(story, dict)
    }


def build_source_stat_rows(articles, briefing):
    """Calculate one collection run's source measurements from gathered material."""
    metrics = defaultdict(lambda: {
        "articles_ingested": 0,
        "articles_in_clusters": 0,
        "clusters_included_in_brief": 0,
        "first_to_report_count": 0,
    })
    for article in articles:
        source_id = article.get("source_id")
        if source_id is not None:
            metrics[source_id]["articles_ingested"] += 1

    included_urls = _included_story_urls(briefing)
    for article_indexes in cluster_articles_for_stats(articles):
        cluster_articles = [articles[index] for index in article_indexes]
        source_ids = {article.get("source_id") for article in cluster_articles if article.get("source_id") is not None}
        included = any(article.get("link", "").rstrip("/") in included_urls for article in cluster_articles)
        for source_id in source_ids:
            metrics[source_id]["articles_in_clusters"] += sum(
                1 for article in cluster_articles if article.get("source_id") == source_id
            )
            if included:
                metrics[source_id]["clusters_included_in_brief"] += 1

        first_article = min(
            cluster_articles,
            key=lambda article: (article.get("timestamp", 0), article.get("link", "")),
        )
        first_source_id = first_article.get("source_id")
        if first_source_id is not None:
            metrics[first_source_id]["first_to_report_count"] += 1
    return dict(metrics)


def record_source_statistics(articles, briefing, target_path=None, report_date=None):
    """Persist a completed collection's source contribution metrics when storage is writable."""
    target = database_path(target_path)
    if not target.is_file():
        return False
    measurements = build_source_stat_rows(articles, briefing)
    if not measurements:
        return False
    stats_date = report_date if isinstance(report_date, str) else (report_date or date.today()).isoformat()
    try:
        with sqlite3.connect(target) as connection:
            for source_id, values in measurements.items():
                connection.execute(
                    """
                    INSERT INTO source_stats (
                        source_id, date, articles_ingested, articles_in_clusters,
                        clusters_included_in_brief, first_to_report_count
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id, date) DO UPDATE SET
                        articles_ingested = source_stats.articles_ingested + excluded.articles_ingested,
                        articles_in_clusters = source_stats.articles_in_clusters + excluded.articles_in_clusters,
                        clusters_included_in_brief = source_stats.clusters_included_in_brief + excluded.clusters_included_in_brief,
                        first_to_report_count = source_stats.first_to_report_count + excluded.first_to_report_count
                    """,
                    (source_id, stats_date, *values.values()),
                )
        return True
    except sqlite3.Error:
        return False


def coverage_matrix(target_path=None):
    """Return the configured region × tier source count matrix, including zero cells."""
    target = database_path(target_path)
    config = load_registry_config()
    matrix = {(region, tier): 0 for region in config["regions"] for tier in range(1, 5)}
    if not target.is_file():
        return matrix
    with sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True) as connection:
        for region, tier, count in connection.execute(
            "SELECT region, tier, COUNT(*) FROM sources WHERE active = 1 GROUP BY region, tier"
        ):
            matrix[(region, tier)] = count
    return matrix


def weekly_source_report(target_path=None, end_date=None):
    """Summarize zero-contribution sources, first reporters, and coverage gaps for seven days."""
    target = database_path(target_path)
    if not target.is_file():
        return {"available": False, "reason": "Source registry database does not exist."}

    period_end = end_date or date.today()
    period_start = date.fromordinal(period_end.toordinal() - 6)
    with sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        measurement_days = connection.execute(
            "SELECT COUNT(DISTINCT date) FROM source_stats WHERE date BETWEEN ? AND ?",
            (period_start.isoformat(), period_end.isoformat()),
        ).fetchone()[0]
        totals = connection.execute(
            """
            SELECT s.id, s.name, s.region, s.tier,
                   COALESCE(SUM(ss.articles_ingested), 0) AS articles_ingested,
                   COALESCE(SUM(ss.articles_in_clusters), 0) AS articles_in_clusters,
                   COALESCE(SUM(ss.clusters_included_in_brief), 0) AS clusters_included_in_brief,
                   COALESCE(SUM(ss.first_to_report_count), 0) AS first_to_report_count
            FROM sources s
            LEFT JOIN source_stats ss ON ss.source_id = s.id AND ss.date BETWEEN ? AND ?
            WHERE s.active = 1
            GROUP BY s.id, s.name, s.region, s.tier
            ORDER BY s.name
            """,
            (period_start.isoformat(), period_end.isoformat()),
        ).fetchall()

    matrix = coverage_matrix(target)
    coverage_gaps = [
        {"region": region, "tier": tier}
        for (region, tier), count in matrix.items()
        if count == 0
    ]
    zero_contribution = [dict(row) for row in totals if row["articles_ingested"] == 0]
    fastest_sources = sorted(
        (dict(row) for row in totals),
        key=lambda row: (row["first_to_report_count"], row["articles_in_clusters"], row["articles_ingested"]),
        reverse=True,
    )[:10]
    return {
        "available": True,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "measurement_days": measurement_days,
        "zero_contribution": zero_contribution,
        "fastest_sources": fastest_sources,
        "coverage_matrix": matrix,
        "coverage_gaps": coverage_gaps,
    }
