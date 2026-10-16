"""Run the briefing pipeline and publish it as a dated archive in ONE commit.

Each run collects the daily and hourly briefings, merges their stories into today's archive
file (briefings/YYYY-MM-DD.json, Europe/Istanbul day) and refreshes briefings/latest.json.
Nothing already archived is removed. When nothing material changed, nothing is committed.
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
from api import story_lifecycle

ALL_MODES = ("daily", "hourly")
STATUS_OK, STATUS_STALE = "ok", "stale"


def timestamp(now=None):
    return (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")


def run_mode(mode):
    """Return (briefing, error_message); exactly one of them is empty."""
    try:
        briefing = _engine.run_pipeline(mode)
        if briefing.get("status") != "ok":
            raise RuntimeError(briefing.get("warning") or "AI briefing generation did not complete")
        print(f"Generated {mode} briefing at {briefing['last_pipeline_run_at']}")
        return briefing, ""
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"[:500]
        print(f"Pipeline failed for {mode}: {error_message}", file=sys.stderr)
        return None, error_message


def status_payload(errors, now):
    return {
        "status": STATUS_STALE if errors else STATUS_OK,
        "errors": errors,
        "last_attempt_at": timestamp(now),
    }


def status_changed(existing, new):
    """last_attempt_at moves every run and must not cause a commit on its own."""
    return (existing or {}).get("status") != new["status"] or (existing or {}).get("errors") != new["errors"]


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


def plan_files(briefings, errors, read, now):
    """Decide which files must be written for this run (possibly none)."""
    config = story_lifecycle.load_badges_config()
    today = story_lifecycle.day_key(now, config)
    day_path = briefing_store.day_path(today)
    existing_day = read(day_path)
    previous_day = read(briefing_store.day_path(story_lifecycle.previous_day_key(today)))
    day = story_lifecycle.build_day(existing_day, previous_day, briefings, now, config)

    files = {}
    if day and story_lifecycle.fingerprint(day) != story_lifecycle.fingerprint(existing_day):
        files[day_path] = day
        files[briefing_store.latest_path()] = day
    new_status = status_payload(errors, now)
    if status_changed(read(briefing_store.status_path()), new_status):
        files[briefing_store.status_path()] = new_status
    return files


def run(modes, out_dir=None, now=None):
    now = now or datetime.now(timezone.utc)
    briefings, errors = {}, {}
    for mode in modes:
        briefing, error = run_mode(mode)
        if briefing:
            briefings[mode] = briefing
        else:
            errors[mode] = error
    try:
        files = plan_files(briefings, errors, make_reader(out_dir), now)
        if not files:
            print("Nothing changed; no commit.")
        elif out_dir:
            print(f"Published ({', '.join(modes)}): {write_local(files, out_dir)}")
        else:
            result = briefing_store.publish(files, f"Publish briefings {timestamp(now)}", repo_dir=PROJECT_DIR)
            print(f"Published ({', '.join(modes)}): {result}")
    except Exception as exc:
        print(f"Publishing failed: {type(exc).__name__}: {exc}"[:600], file=sys.stderr)
        return 1
    return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", default="all", choices=("all", *ALL_MODES))
    parser.add_argument("--out-dir", help="read and write files here instead of the store (dry run)")
    args = parser.parse_args()
    modes = ALL_MODES if args.mode == "all" else (args.mode,)
    return run(modes, args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
