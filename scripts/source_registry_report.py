"""Create or audit the local SQLite source registry without changing source activation."""

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from api import _engine
from api import source_registry


def distribution_rows(database):
    with sqlite3.connect(database) as connection:
        return connection.execute(
            """
            SELECT region, tier, COUNT(*) AS source_count
            FROM sources
            WHERE active = 1
            GROUP BY region, tier
            ORDER BY region, tier
            """
        ).fetchall()


def render_report(database):
    matrix = source_registry.coverage_matrix(database)
    config = source_registry.load_registry_config()
    report = [
        "# Source Registry Audit",
        "",
        "## Active source distribution",
        "",
        "| Region | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Total |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for region in config["regions"]:
        counts = [matrix[(region, tier)] for tier in range(1, 5)]
        report.append(f"| {region} | " + " | ".join(str(count) for count in counts) + f" | {sum(counts)} |")

    report.extend(["", "## Coverage gaps", ""])
    gaps = [
        f"- {region}: Tier {tier}"
        for (region, tier), count in matrix.items()
        if count == 0
    ]
    report.extend(gaps or ["- No region × tier cell is empty."])

    weekly = source_registry.weekly_source_report(database)
    report.extend(["", "## Weekly source performance", ""])
    if not weekly["available"]:
        report.append(f"- {weekly['reason']}")
    else:
        report.append(f"Period: {weekly['period_start']} to {weekly['period_end']}")
        report.append(f"Recorded collection days: {weekly['measurement_days']}")
        report.extend(["", "### No contribution in recorded collection days", ""])
        report.extend(
            [f"- {source['name']} ({source['region']}, Tier {source['tier']})" for source in weekly["zero_contribution"]]
            or ["- No active source has zero recorded ingestion in this period."]
        )
        report.extend(["", "### Fastest reporters", "", "| Source | First reports | Cluster articles | Ingested |", "| --- | ---: | ---: | ---: |"])
        for source in weekly["fastest_sources"]:
            report.append(
                f"| {source['name']} | {source['first_to_report_count']} | "
                f"{source['articles_in_clusters']} | {source['articles_ingested']} |"
            )
        report.extend([
            "",
            "First-to-report is a clustering-preliminary measurement based on conservative title similarity across material collected by this app; it is not a claim about the entire market and is not used in scoring.",
        ])
    return "\n".join(report) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=source_registry.database_path())
    parser.add_argument("--report", type=Path, default=PROJECT_DIR / "reports" / "source_registry_audit.md")
    args = parser.parse_args()

    database = source_registry.migrate_sources(_engine.get_builtin_source_records(), args.database)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(database), encoding="utf-8")
    print(f"Registry migrated: {database}")
    print(f"Audit report: {args.report}")
    print(f"Active sources: {sum(count for _, _, count in distribution_rows(database))}")


if __name__ == "__main__":
    main()
