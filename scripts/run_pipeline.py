"""Run the briefing pipeline once and publish it as a dated archive in ONE commit.

Runs every 3 hours: at 08:00 Europe/Istanbul performs a deep search and refreshes today's daily stories
from scratch; subsequent 3-hour runs append newly discovered stories into today's archive file
(briefings/YYYY-MM-DD.json, Europe/Istanbul day) -> narratives for stories that have none -> publish.

Failure semantics: only a real collection failure (or a publish failure) fails the run and writes
status "stale". An LLM failure just leaves narrative_status="pending" for the next run.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from api import _engine
from api import briefing_store
from api import narrative
from api import source_catalog
from api import source_retry
from api import source_recovery
from api import story_lifecycle
from api import urls
from api import airspace_radar
from api import earnings_calendar
from api import fleet_watch

STATUS_OK, STATUS_STALE = "ok", "stale"
STATUS_FETCH_ERROR = "error"
HEADLINE_ONLY = "headline_only"
HEARTBEAT_HOURS = 3      # source health is written at least this often even when nothing else changed


def timestamp(now=None):
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def collect(recovered=None):
    """Return (collected, error_message); exactly one of them is empty. `recovered`: sources the weekly retry brought back."""
    try:
        return (_engine.collect_run(recovered=recovered) if recovered else _engine.collect_run()), ""
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:500]
        print(f"Collection failed: {message}", file=sys.stderr)
        return None, message


def day_payload(collected, now):
    head = _engine.build_briefing_payload("daily", [], status="ok")
    radar = collected.get("airspace_radar") or airspace_radar.load_radar(now=now)
    calendar = collected.get("earnings_calendar") or earnings_calendar.load_calendar(now=now)
    fleet = collected.get("fleet_watch") or fleet_watch.load_fleet_watch()
    payload = {**head, "market": collected["market"], "airspace_radar": radar, "earnings_calendar": calendar, "fleet_watch": fleet, "last_pipeline_run_at": timestamp(now), "stories": collected["stories"]}
    if collected.get("morning_deep_scan") or story_lifecycle.is_morning_deep_window(now):
        payload["morning_deep_scan"] = True
    if collected.get("force_morning_reset"):
        payload["force_morning_reset"] = True
    return payload


def source_health(source_report, existing_status, now, retry=None):
    """Per source: last status, last successful read and articles in the last 24 hours. Unresolved sources only show up here."""
    report = dict(source_report or {})
    for row in source_catalog.read_rows():
        report.setdefault(row["name"], {"status": row["status"], "error": row["reason"], "articles": 0})
    previous = (existing_status or {}).get("sources", {})
    health = {}
    for name, entry in sorted(report.items()):
        read_ok = entry["status"] == "active" and not entry.get("error")
        health[name] = {
            "status": entry["status"] if (read_ok or entry["status"] != "active") else STATUS_FETCH_ERROR,
            "last_ok_at": timestamp(now) if read_ok else previous.get(name, {}).get("last_ok_at", ""),
            "articles_24h": entry.get("articles_24h", 0),
            "error": entry.get("error", ""),
        }
        prior = previous.get(name, {})
        for key in ("last_retry_at", "retry_feed", "recovered_at", "retry_note"):
            if key in prior:
                health[name][key] = prior[key]
        attempt = (retry or {}).get(name)
        if attempt:
            health[name]["last_retry_at"] = attempt["at"]
            if attempt["valid"]:
                health[name].update(retry_feed={"feed_url": attempt["feed_url"], "method": attempt["method"]}, recovered_at=attempt["at"])
                health[name].pop("retry_note", None)
            else:
                health[name]["retry_note"] = attempt["reason"]
    return health


def source_summary(health):
    ok = sum(1 for entry in health.values() if entry["status"] == "active")
    return {"sources": len(health), "reading_ok": ok, "unresolved": len(health) - ok}


def status_payload(collection_error, narrative_report, now, collected=None, existing_status=None, retry=None):
    payload = {
        "status": STATUS_STALE if collection_error else STATUS_OK,
        "errors": {"collect": collection_error} if collection_error else {},
        "narrative_pending": narrative_report["pending"],
        "narrative_error": narrative_report["error"],
        "narrative_calls": narrative_report["calls"],
        "last_attempt_at": timestamp(now),
    }
    if collected is not None:
        health = source_health(collected.get("source_report"), existing_status, now, retry)
        payload.update(sources=health, source_summary=source_summary(health))
    elif existing_status and "sources" in existing_status:
        payload.update(sources=existing_status["sources"], source_summary=existing_status.get("source_summary", {}))
    return payload


def status_changed(existing, new, now=None):
    """Timestamps, call counts and error wording move every run and must not cause a commit on their own. A source's
    status flipping does; so does a stale heartbeat, so the per-source times in status.json never go more than HEARTBEAT_HOURS old."""
    keys = ("status", "errors", "narrative_pending")
    if any((existing or {}).get(key) != new[key] for key in keys):
        return True
    old_sources = {name: entry["status"] for name, entry in (existing or {}).get("sources", {}).items()}
    if old_sources != {name: entry["status"] for name, entry in new.get("sources", {}).items()}:
        return True
    last = story_lifecycle.parse_iso((existing or {}).get("last_attempt_at"))
    current = story_lifecycle.parse_iso(new["last_attempt_at"])
    return bool(new.get("sources") and (last is None or (current - last).total_seconds() >= HEARTBEAT_HOURS * 3600))


def write_local(files, out_dir):
    for pathname, payload in files.items():
        target = Path(out_dir) / pathname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"local: {len(files)} files in {out_dir}"


def make_reader(out_dir):
    """Where the pipeline reads the files it is about to update: the store, or the dry-run folder."""
    if not out_dir:
        return lambda pathname: briefing_store.read_for_update(pathname, repo_dir=PROJECT_DIR)

    def read_local(pathname):
        path = Path(out_dir) / pathname
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    return read_local


def plan_files(collected, collection_error, read, now, api_key, narrate=narrative.fill_pending, retry=None):
    """Decide which files must be written for this run (possibly none). Returns (files, narrative_report)."""
    config = story_lifecycle.load_badges_config()
    today = story_lifecycle.day_key(now, config)
    day_path = briefing_store.day_path(today)
    existing_day = read(day_path)
    previous_day = read(briefing_store.day_path(story_lifecycle.previous_day_key(today)))
    briefings = {"daily": day_payload(collected, now)} if collected else {}
    reconciled_day, recovered_count = source_recovery.reconcile_day(
        existing_day, (collected or {}).get("verification_candidates", []), now
    )
    day = story_lifecycle.build_day(reconciled_day, previous_day, briefings, now, config)

    report = {"calls": 0, "narrated": 0, "pending": 0, "error": ""}
    if day:
        description_limit = _engine.load_description_limit()
        story_lifecycle.present_stories(day, now, config)

        # Unshorten any Google News URLs on active stories into direct publisher links
        for story in day.get("stories", []):
            orig = story.get("original_source") or {}
            orig_url = orig.get("url", "")
            if "news.google.com" in orig_url:
                res = urls.unshorten_google_news_url(orig_url)
                if res and res != orig_url:
                    orig["url"] = res
                    story["original_source"] = orig
            for entry in story.get("sources", []):
                entry_url = entry.get("url", "")
                if "news.google.com" in entry_url:
                    res = urls.unshorten_google_news_url(entry_url)
                    if res:
                        entry["url"] = res
            if not story.get("image_url"):
                target_url = (story.get("original_source") or {}).get("url", "")
                is_restricted = (
                    story.get("license_required")
                    or story.get("license_status") == "paid"
                    or (story.get("original_source") or {}).get("license_required")
                    or (story.get("original_source") or {}).get("license_status") == "paid"
                )
                if target_url and "news.google.com" not in target_url and not is_restricted:
                    story["image_url"] = _engine.fetch_og_image(target_url)
        # The archive-only low band costs no LLM calls; it is narrated if its score ever reaches the list.
        # A headline-only story's publisher summary is held in memory for the model call and never written to the archive.
        incoming = {item["story_id"]: item for item in (collected or {}).get("stories", [])}
        for story in day["stories"]:
            if story.get("basis") == HEADLINE_ONLY and not story.get("source_description") and story["story_id"] in incoming:
                story["source_description"] = incoming[story["story_id"]].get("source_description", "")
        relevance = story_lifecycle.load_relevance_config()
        report = narrate([story for story in day["stories"] if story_lifecycle.is_listed(story)
                          and not story_lifecycle.is_excluded(story, relevance)], api_key, description_limit, now=now)
        for story in day["stories"]:
            if story.get("basis") == HEADLINE_ONLY:
                story["source_description"] = ""
                story["article_body"] = ""
            if story.get("license_required") or story.get("license_status") == "paid":
                story["source_description"] = ""
                story["article_body"] = ""

    files = {}
    if day and story_lifecycle.fingerprint(day) != story_lifecycle.fingerprint(existing_day):
        files[day_path] = day
        files[briefing_store.latest_path()] = day
    existing_status = read(briefing_store.status_path())
    if recovered_count:
        print(f"Source verification: recovered={recovered_count}")
    new_status = status_payload(collection_error, report, now, collected, existing_status, retry)
    if status_changed(existing_status, new_status):
        files[briefing_store.status_path()] = new_status
    return files, report


OVERRIDES_PATH = PROJECT_DIR / "config" / "source_status_overrides.json"


def weekly_retry(read, now):
    """Retry the sources that are disabled_blocked (once per source per week, one request each). Returns (results, recovered).
    Whatever goes wrong here is logged and ignored: a retry never fails the run."""
    try:
        previous_status = read(briefing_store.status_path())
        overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8")) if OVERRIDES_PATH.is_file() else {}
        results = source_retry.retry_blocked(source_catalog.read_rows(), previous_status, overrides, now)
        return results, source_retry.recovered_sources(previous_status, results)
    except Exception as exc:
        print(f"Weekly source retry skipped: {type(exc).__name__}: {exc}"[:300], file=sys.stderr)
        return {}, {}


def run(out_dir=None, now=None, api_key=None, narrate=narrative.fill_pending, force_morning_reset=False):
    now = now or datetime.now(timezone.utc)
    api_key = _engine.GEMINI_API_KEY if api_key is None else api_key
    reader = make_reader(out_dir)
    retry, recovered = weekly_retry(reader, now)
    collected, collection_error = collect(recovered)
    if collected and force_morning_reset:
        collected["morning_deep_scan"] = True
        collected["force_morning_reset"] = True
    try:
        if collected and force_morning_reset:
            # Propagate force_morning_reset into day_payload
            pass
        files, report = plan_files(collected, collection_error, reader, now, api_key, narrate, retry)
        print(f"Narratives: calls={report['calls']} narrated={report['narrated']} pending={report['pending']}"
              + (f" (LLM unavailable: {report['error']}; will retry next run)" if report["error"] else ""))
        if not files:
            print("Nothing changed; no commit.")
        elif out_dir:
            print(f"Published: {write_local(files, out_dir)}")
        else:
            print(f"Published: {briefing_store.publish(files, f'Publish briefings {timestamp(now)}', repo_dir=PROJECT_DIR)}")
    except Exception as exc:
        print(f"Publishing failed: {type(exc).__name__}: {exc}"[:600], file=sys.stderr)
        return 1
    return 1 if collection_error else 0


def _should_skip_unscheduled_cloud_trigger(now):
    """When an external hourly webhook triggers workflow_dispatch every hour, only run on the 3-hour schedule
    (02, 05, 08, 11, 14, 17, 20, 23 Europe/Istanbul) so off-hours do not consume LLM quota."""
    import os
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return False
    config = story_lifecycle.load_badges_config()
    local_now = now.astimezone(story_lifecycle.local_timezone(config))
    reset_hour = int(config.get("morning_deep_reset_hour_local", story_lifecycle.MORNING_RESET_HOUR_LOCAL))
    interval = int(config.get("scan_interval_hours", story_lifecycle.SCAN_INTERVAL_HOURS))
    return (local_now.hour - reset_hour) % interval != 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", help="read and write files here instead of the store (dry run)")
    parser.add_argument("--force-morning-reset", action="store_true", help="force a full 08:00 morning deep reset")
    parser.add_argument("--force", action="store_true", help="force run even during off-hours")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if not args.force and not args.force_morning_reset and not args.out_dir and _should_skip_unscheduled_cloud_trigger(now):
        print("Skipping off-hour trigger; next scan runs on the 3-hour schedule (08, 11, 14, 17, 20, 23, 02, 05 Europe/Istanbul).")
        return 0
    return run(args.out_dir, now=now, force_morning_reset=args.force_morning_reset)


if __name__ == "__main__":
    raise SystemExit(main())
