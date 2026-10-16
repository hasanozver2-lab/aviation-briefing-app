"""Test only HTTP accessibility of inactive primary-financial source candidates."""

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_DIR / "config" / "financial_source_candidates.json"
DEFAULT_REPORT = PROJECT_DIR / "reports" / "financial_source_access.md"


def probe_candidate(candidate):
    user_agent = "AeroBrief source research contact@example.com"
    request = urllib.request.Request(candidate["url"], method="HEAD", headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.headers.get_content_type(), "HEAD"
    except urllib.error.HTTPError as exc:
        if exc.code not in {403, 405, 501}:
            return exc.code, "", "HEAD"
    except urllib.error.URLError as exc:
        return 0, "", type(exc.reason).__name__

    request = urllib.request.Request(candidate["url"], headers={"User-Agent": user_agent, "Range": "bytes=0-1023"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read(1024)
            return response.status, response.headers.get_content_type(), "GET-range"
    except urllib.error.HTTPError as exc:
        return exc.code, "", "GET-range"
    except urllib.error.URLError as exc:
        return 0, "", type(exc.reason).__name__


def render_report(candidates, results):
    report = [
        "# Primary Financial Source Access Review",
        "",
        f"Checked at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "All candidates are inactive. No adapter, feed ingestion, body storage, or publication is enabled by this check.",
        "",
        "| Candidate | HTTP | Content type | Test | Adapter | Usage review |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for candidate, result in zip(candidates, results):
        status, content_type, method = result
        adapter = "Required" if candidate.get("adapter_required") else "Not required"
        report.append(
            f"| {candidate['name']} | {status or 'network error'} | {content_type or '-'} | {method} | {adapter} | {candidate['usage_terms']} |"
        )
    report.extend([
        "",
        "## Implementation boundary",
        "",
        "- SEC EDGAR is the only confirmed structured public API in this review. A future adapter must request only configured airline/manufacturer CIKs, use a real contact-bearing User-Agent, and rate-limit below the SEC maximum.",
        "- The airline IR and KAP candidates are public pages, not approved machine feeds. They remain inactive until a separate adapter and source-specific reuse review are approved.",
    ])
    return "\n".join(report) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    candidates = json.loads(args.config.read_text(encoding="utf-8"))["candidates"]
    if any(candidate.get("active") for candidate in candidates):
        raise ValueError("financial source candidates must remain inactive")
    results = [probe_candidate(candidate) for candidate in candidates]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(candidates, results), encoding="utf-8")
    for candidate, result in zip(candidates, results):
        print(f"{candidate['name']}: {result[0] or 'network error'}")


if __name__ == "__main__":
    main()
