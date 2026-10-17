"""Probe every catalog source from THIS computer and compare the result with the GitHub runner's.

Read-only: it never writes to the briefing-data branch, the archive, status.json, the catalog or any secret. It writes one report,
reports/probe_local.json, and prints a summary of which sources open only from your own network.

Same rules as the runner probe: the self-identifying User-Agent, robots.txt (wildcards included), one request at a time per host
(different hosts in parallel). Usage: python scripts/probe_local.py [--out reports/probe_local.json] [--runner reports/source_probe.json] [--only "Name A,Name B"]
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

ACCESSIBLE = "active"


def local_record(record):
    """The fields worth keeping from one probe record."""
    return {key: record[key] for key in ("name", "source_type", "status", "reason", "method", "http_code", "seconds", "items_7d", "items_90d", "robots")}


def compare(local_records, runner_records):
    """Which sources open only from this computer, only from the runner, from both, from neither."""
    runner = {record["name"]: record for record in runner_records}
    groups = {"only_local": [], "only_runner": [], "both": [], "neither": [], "not_in_runner_probe": []}
    for record in local_records:
        other = runner.get(record["name"])
        if other is None:
            groups["not_in_runner_probe"].append(record["name"])
            continue
        here, there = record["status"] == ACCESSIBLE, other["status"] == ACCESSIBLE
        groups["both" if here and there else "only_local" if here else "only_runner" if there else "neither"].append(record["name"])
    return groups


def summary_lines(groups, local_records, runner_records):
    local = {record["name"]: record for record in local_records}
    runner = {record["name"]: record for record in runner_records}
    lines = [f"Local probe: {sum(1 for r in local_records if r['status'] == ACCESSIBLE)} of {len(local_records)} sources open from this computer; "
             f"{sum(1 for r in runner_records if r['status'] == ACCESSIBLE)} of {len(runner_records)} from the GitHub runner.",
             f"  open from both: {len(groups['both'])} | only from this computer: {len(groups['only_local'])} | only from the runner: {len(groups['only_runner'])} | from neither: {len(groups['neither'])}"]
    if groups["only_local"]:
        lines.append("Open only from your network (blocked or failing on the runner):")
        for name in groups["only_local"]:
            lines.append(f"  {name}: here {local[name]['method'] or '-'} http={local[name]['http_code']} 90d={local[name]['items_90d']} | runner {runner[name]['status']} ({runner[name]['reason'][:60]})")
    if groups["only_runner"]:
        lines.append("Open only from the runner: " + ", ".join(groups["only_runner"]))
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(PROJECT_DIR / "reports" / "probe_local.json"))
    parser.add_argument("--runner", default=str(PROJECT_DIR / "reports" / "source_probe.json"), help="the runner's probe output to compare with")
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
    records, _ = source_probe.probe_all(rows, builtin, feed_sources.load_discovered(), now, legacy_fetch=legacy_fetch)
    local_records = [local_record(record) for record in records]
    runner_path = Path(args.runner)
    runner_records = json.loads(runner_path.read_text(encoding="utf-8"))["sources"] if runner_path.is_file() else []
    groups = compare(local_records, runner_records) if runner_records else {}
    report = {"generated_at": now.isoformat(timespec="seconds"), "where": "the computer that ran this script", "platform": platform.platform(), "python": platform.python_version(),
              "user_agent": feed_discovery.USER_AGENT, "duration_seconds": round(time.monotonic() - started, 1), "sources": local_records, "comparison": groups}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out} ({len(local_records)} sources, {report['duration_seconds']} s)")
    if runner_records:
        print("\n".join(summary_lines(groups, local_records, runner_records)))
    else:
        print(f"no runner probe at {runner_path}; nothing to compare with")
    return 0


if __name__ == "__main__":
    sys.exit(main())
