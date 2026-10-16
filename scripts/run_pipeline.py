"""Run the briefing pipeline once and publish it as a dated archive in ONE commit.

One hourly run does: collect (no LLM) -> score, select and merge into today's archive file
(briefings/YYYY-MM-DD.json, Europe/Istanbul day) -> narratives for stories that have none (one
batched, retried LLM call at most twice) -> publish. Daily and hourly are views of the same archive.

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
from api import story_lifecycle

STATUS_OK, STATUS_STALE = "ok", "stale"


def timestamp(now=None):
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def collect():
    """Return (collected, error_message); exactly one of them is empty."""
    try:
        return _engine.collect_run(), ""
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:500]
        print(f"Collection failed: {message}", file=sys.stderr)
        return None, message


def day_payload(collected, now):
    head = _engine.build_briefing_payload("daily", [], status="ok")
    return {**head, "market": collected["market"], "last_pipeline_run_at": timestamp(now), "stories": collected["stories"]}


def status_payload(collection_error, narrative_report, now):
    return {
        "status": STATUS_STALE if collection_error else STATUS_OK,
        "errors": {"collect": collection_error} if collection_error else {},
        "narrative_pending": narrative_report["pending"],
        "narrative_error": narrative_report["error"],
        "narrative_calls": narrative_report["calls"],
        "last_attempt_at": timestamp(now),
    }


def status_changed(existing, new):
    """Timestamps, call counts and error wording move every run and must not cause a commit on their own."""
    keys = ("status", "errors", "narrative_pending")
    return any((existing or {}).get(key) != new[key] for key in keys)


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


def plan_files(collected, collection_error, read, now, api_key, narrate=narrative.fill_pending):
    """Decide which files must be written for this run (possibly none). Returns (files, narrative_report)."""
    config = story_lifecycle.load_badges_config()
    today = story_lifecycle.day_key(now, config)
    day_path = briefing_store.day_path(today)
    existing_day = read(day_path)
    previous_day = read(briefing_store.day_path(story_lifecycle.previous_day_key(today)))
    briefings = {"daily": day_payload(collected, now)} if collected else {}
    day = story_lifecycle.build_day(existing_day, previous_day, briefings, now, config)

    report = {"calls": 0, "narrated": 0, "pending": 0, "error": ""}
    if day:
        description_limit = _engine.load_description_limit()
        story_lifecycle.present_stories(day, now, config)
        # The archive-only low band costs no LLM calls; it is narrated if its score ever reaches the list.
        report = narrate([story for story in day["stories"] if story_lifecycle.is_listed(story)], api_key, description_limit, now=now)

    files = {}
    if day and story_lifecycle.fingerprint(day) != story_lifecycle.fingerprint(existing_day):
        files[day_path] = day
        files[briefing_store.latest_path()] = day
    new_status = status_payload(collection_error, report, now)
    if status_changed(read(briefing_store.status_path()), new_status):
        files[briefing_store.status_path()] = new_status
    return files, report


def run(out_dir=None, now=None, api_key=None, narrate=narrative.fill_pending):
    now = now or datetime.now(timezone.utc)
    api_key = _engine.GEMINI_API_KEY if api_key is None else api_key
    collected, collection_error = collect()
    try:
        files, report = plan_files(collected, collection_error, make_reader(out_dir), now, api_key, narrate)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", help="read and write files here instead of the store (dry run)")
    args = parser.parse_args()
    return run(args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
