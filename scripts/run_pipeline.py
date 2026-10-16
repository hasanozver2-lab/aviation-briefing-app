"""Run the briefing pipeline for one or both modes and publish the results in ONE commit.

The default store is the git data branch (BRIEFING_STORE=github); see api/briefing_store.py.
A failing mode keeps its last good briefing and only gets a "stale" status file.
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

ALL_MODES = ("daily", "hourly")


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def status_payload(mode, status, last_pipeline_run_at="", error=""):
    return {
        "mode": mode,
        "status": status,
        "last_pipeline_run_at": last_pipeline_run_at,
        "last_attempt_at": timestamp(),
        "error": error,
    }


def run_mode(mode):
    """Return ({pathname: payload}, error_message); the error is empty on success."""
    try:
        briefing = _engine.run_pipeline(mode)
        if briefing.get("status") != "ok":
            raise RuntimeError(briefing.get("warning") or "AI briefing generation did not complete")
        completed_at = briefing["last_pipeline_run_at"]
        files = {
            briefing_store.briefing_path(mode): briefing,
            briefing_store.pipeline_status_path(mode): status_payload(mode, "ok", completed_at),
        }
        print(f"Generated {mode} briefing at {completed_at}")
        return files, ""
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"[:500]
        print(f"Pipeline failed for {mode}: {error_message}", file=sys.stderr)
        return {briefing_store.pipeline_status_path(mode): status_payload(mode, "stale", error=error_message)}, error_message


def write_local(files, out_dir):
    for pathname, payload in files.items():
        target = Path(out_dir) / pathname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"local: {len(files)} files in {out_dir}"


def run(modes, out_dir=None):
    files, failures = {}, []
    for mode in modes:
        mode_files, error = run_mode(mode)
        files.update(mode_files)
        if error:
            failures.append(mode)
    try:
        if out_dir:
            result = write_local(files, out_dir)
        else:
            result = briefing_store.publish(files, f"Publish briefings {timestamp()}", repo_dir=PROJECT_DIR)
        print(f"Published ({', '.join(modes)}): {result}")
    except Exception as exc:
        print(f"Publishing failed: {type(exc).__name__}: {exc}"[:600], file=sys.stderr)
        return 1
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", default="all", choices=("all", *ALL_MODES))
    parser.add_argument("--out-dir", help="write files here instead of publishing (dry run)")
    args = parser.parse_args()
    modes = ALL_MODES if args.mode == "all" else (args.mode,)
    return run(modes, args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
