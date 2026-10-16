"""Run one briefing mode in GitHub Actions and publish only completed JSON to Vercel Blob."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from api import _engine
from api import blob_store


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def publish_status(mode, status, last_pipeline_run_at="", error=""):
    return blob_store.put_public_json(blob_store.pipeline_status_path(mode), {
        "mode": mode,
        "status": status,
        "last_pipeline_run_at": last_pipeline_run_at,
        "last_attempt_at": timestamp(),
        "error": error,
    })


def run(mode):
    try:
        briefing = _engine.run_pipeline(mode)
        if briefing.get("status") != "ok":
            raise RuntimeError(briefing.get("warning") or "AI briefing generation did not complete")
        completed_at = briefing["last_pipeline_run_at"]
        blob_store.put_public_json(blob_store.briefing_path(mode), briefing)
        publish_status(mode, "ok", completed_at)
        print(f"Published {mode} briefing at {completed_at}")
        return 0
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"[:500]
        print(f"Pipeline failed for {mode}: {error_message}", file=sys.stderr)
        try:
            publish_status(mode, "stale", error=error_message)
        except Exception as status_exc:
            print(f"Could not publish stale status: {type(status_exc).__name__}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("daily", "hourly"))
    return run(parser.parse_args().mode)


if __name__ == "__main__":
    raise SystemExit(main())
