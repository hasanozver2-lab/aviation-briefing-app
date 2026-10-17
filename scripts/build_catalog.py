"""Merge config/source_expansion.json into config/sources.csv (idempotent). Usage: python scripts/build_catalog.py [--check]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api import source_catalog  # noqa: E402


def main(argv):
    expansion = source_catalog.json.loads(source_catalog.EXPANSION_PATH.read_text(encoding="utf-8"))
    rows, report = source_catalog.merge_expansion(source_catalog.read_rows(), expansion)
    print({key: len(value) for key, value in report.items()})
    for key in ("merged_same_domain",):
        for item in report[key]:
            print("  same domain:", item)
    if "--check" in argv:
        return 0
    source_catalog.write_rows(rows)
    print(f"wrote {len(rows)} rows to {source_catalog.SOURCES_CSV_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
