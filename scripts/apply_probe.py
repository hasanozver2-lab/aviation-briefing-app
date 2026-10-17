"""Apply a downloaded probe output: statuses in config/sources.csv, config/feeds_discovered.json, reports/source_probe.json.

Usage: python scripts/apply_probe.py path/to/source_probe.json
This is the ONLY writer of config/feeds_discovered.json (the daily pipeline only reads it).
"""

import json
import shutil
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from api import feed_sources, source_catalog, source_probe  # noqa: E402

TERMS_REVIEW_PATH = PROJECT_DIR / "config" / "source_terms_review.json"
OVERRIDES_PATH = PROJECT_DIR / "config" / "source_status_overrides.json"
REPORT_COPY_PATH = PROJECT_DIR / "reports" / "source_probe.json"


def main(argv):
    probe_path = Path(argv[0])
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    terms = json.loads(TERMS_REVIEW_PATH.read_text(encoding="utf-8"))
    overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    rows, discovered, changes = source_probe.apply_probe(source_catalog.read_rows(), probe, terms, feed_sources.load_discovered(), overrides=overrides)
    source_catalog.write_rows(rows)
    feed_sources.write_discovered(discovered)
    REPORT_COPY_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(probe_path, REPORT_COPY_PATH)
    print(f"{len(rows)} sources, {len(discovered)} verified feed addresses, {len(changes)} status changes")
    for name, before, after, reason in changes:
        print(f"  {name}: {before} -> {after} {reason[:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
