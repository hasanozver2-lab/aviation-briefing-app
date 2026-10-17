"""Probe every catalog source (run by .github/workflows/source-probe.yml on a GitHub runner; also usable locally).

Writes one JSON file with, per source: discovery method, HTTP code, time, items in the last 7 days, how many pass the
aviation filter, score above min_score and would be listed, plus clusters of the same event across sources and near misses.
Never touches briefing data, the archive or the briefing-data branch.
"""

import argparse
import json
import platform
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from api import _engine, feed_discovery, feed_sources, source_catalog, source_probe  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="probe-output/source_probe.json")
    parser.add_argument("--only", help="comma separated source names (debugging)")
    args = parser.parse_args(argv)
    started = time.monotonic()
    rows = source_catalog.read_rows()
    if args.only:
        wanted = {name.strip() for name in args.only.split(",")}
        rows = [row for row in rows if row["name"] in wanted]
    builtin = {source["name"]: source for source in _engine.get_builtin_source_records()}
    headers = {"User-Agent": feed_discovery.USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/html;q=0.8, */*;q=0.5"}
    legacy_fetch = lambda source, cutoff: _engine._fetch_source_articles(source, cutoff, headers)
    now = source_probe.utc_now()
    records, articles = source_probe.probe_all(rows, builtin, feed_sources.load_discovered(), now, legacy_fetch=legacy_fetch)
    records, clusters, near_misses = source_probe.measure(articles, records)
    probe = {
        "generated_at": now.isoformat(timespec="seconds"), "runner": {"platform": platform.platform(), "python": platform.python_version()},
        "duration_seconds": round(time.monotonic() - started, 1), "user_agent": feed_discovery.USER_AGENT,
        "summary": {"sources": len(records), "by_status": {status: sum(1 for r in records if r["status"] == status) for status in sorted({r["status"] for r in records})},
                    "articles_7d": len(articles)},
        "sources": records, "clusters": clusters, "near_misses": near_misses,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(probe, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(probe["summary"], ensure_ascii=False), f"in {probe['duration_seconds']} s -> {out}")
    for record in records:
        print(f"{record['name'][:38]:38} {record['status']:20} {record['method'] or '-':14} http={record['http_code']:<4} {record['seconds']:>6}s 7d={record['items_7d']:<3} listed={record['listed']:<3} {record['reason'][:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
