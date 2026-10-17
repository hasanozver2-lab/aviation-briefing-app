"""Read-only coverage measurement: no narratives, registry writes or data-branch publication."""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from api import _engine, briefing_store, feed_discovery as fd, feed_sources, entities, source_catalog, source_probe, story_lifecycle

TARGETS = ("IATA Press Room", "ICAO Newsroom", "ACI World News", "The New York Times", "BBC News Business")


def measure_source(row, discovered, now, index):
    source = feed_sources.source_record(row)
    reader = fd.PoliteFetcher(timeout=source["timeout_s"])
    address = discovered[source["slug"]]["feed_url"]
    record = {"name": row["name"], "source_type": row["source_type"], "mode": row["mode"],
              "official": source["official"], "aviation_filter": source["aviation_filter"], "feed_url": address}
    if not reader.allowed(address):
        return {**record, "status": "excluded_policy", "items_7d": 0, "error": "robots.txt disallows feed"}, []
    articles, health = feed_sources.read_source(source, discovered, reader, now, now - timedelta(days=90))
    week = [item for item in articles if item["timestamp"] >= (now - timedelta(days=7)).timestamp()]
    record.update(status=health["status"], error=health["error"], read_90d=len(articles), items_7d=len(week),
                  raw_48h=sum(item["timestamp"] >= (now - timedelta(hours=48)).timestamp() for item in articles),
                  latest_published_at=max((datetime.fromtimestamp(item["timestamp"], timezone.utc).isoformat() for item in articles), default=None))
    relevant = week
    if source["aviation_filter"]:
        relevant, _ = feed_sources.filter_for_aviation(week, index)
    selected = relevant[:feed_sources.MAX_ITEMS_PER_SOURCE]
    record["aviation_7d_before_limit"] = len(relevant)
    record["aviation_48h"] = sum(item["timestamp"] >= (now - timedelta(hours=48)).timestamp() for item in selected)
    record["examples"] = [{"title": item["title"], "url": item["link"]} for item in selected[:3]]
    return record, selected


def run():
    now = fd.utc_now()
    rows = {row["name"]: row for row in source_catalog.read_rows()}
    discovered = feed_sources.load_discovered()
    index = entities.EntityIndex.from_csv()
    records, articles = [], []
    for name in TARGETS:
        record, selected = measure_source(rows[name], discovered, now, index)
        records.append(record)
        articles.extend(selected)
    records, clusters, _ = source_probe.measure(articles, records)
    candidates = [_engine.build_candidate_story(article, number) for number, article in
                  enumerate(story_lifecycle.cluster_representatives(articles), start=1)]
    story_lifecycle.enrich_stories(candidates, articles)
    relevance = story_lifecycle.load_relevance_config()
    evaluated = [{"headline": story["headline"], "event_type": story.get("event_type"),
                  "score": story["relevance_score"], "sources": [source["name"] for source in story["sources"]],
                  "listed": story["relevance_score"] >= relevance["selection"]["min_score"] and not story_lifecycle.is_excluded(story, relevance)}
                 for story in candidates]
    status = briefing_store.read_json(briefing_store.status_path())
    alerts = (status or {}).get("sources", {}).get("Google Alerts (wire headlines)", {})
    return {"checked_at": now.isoformat(timespec="seconds"), "window_days": 7,
            "note": "7-day diagnostic window, not a change to the pipeline's 48-hour collection window. Scores and thresholds unchanged.",
            "sources": records, "clusters": clusters, "evaluated_stories": evaluated,
            "alerts": {key: alerts.get(key) for key in ("status", "last_ok_at", "articles_24h")},
            "direct_access": {name: {"status": rows[name]["status"], "reason": rows[name]["reason"]}
                              for name in ("Reuters Aviation", "Bloomberg Aviation", "CNBC Airlines", "Eurocontrol News")}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON report destination")
    args = parser.parse_args()
    result = run()
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
