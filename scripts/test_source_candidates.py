"""Test proposed source feeds and report results without activating any candidate."""

import json
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
CANDIDATES_PATH = PROJECT_DIR / "config" / "source_candidates.json"
DEFAULT_REPORT_PATH = PROJECT_DIR / "reports" / "source_candidate_access.md"
USER_AGENT = "AeroBrief source registry validation/1.0"
TIMEOUT_SECONDS = 12


def probe_candidate(candidate):
    feed_url = str(candidate.get("feed_url") or "").strip()
    if not feed_url:
        return {
            "status": "not_testable_without_licensed_endpoint",
            "http_status": "-",
            "content_type": "-",
            "latency_ms": "-",
            "detail": "No public feed URL is configured.",
        }

    started_at = time.perf_counter()
    try:
        request = urllib.request.Request(
            feed_url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.9"},
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            content = response.read(1_000_000)
            content_type = response.headers.get_content_type()
            status_code = response.status
    except urllib.error.HTTPError as error:
        return {
            "status": "unreachable",
            "http_status": error.code,
            "content_type": error.headers.get_content_type() if error.headers else "-",
            "latency_ms": round((time.perf_counter() - started_at) * 1000),
            "detail": f"HTTP {error.code}",
        }
    except Exception as error:
        return {
            "status": "unreachable",
            "http_status": "-",
            "content_type": "-",
            "latency_ms": round((time.perf_counter() - started_at) * 1000),
            "detail": type(error).__name__,
        }

    result = {
        "http_status": status_code,
        "content_type": content_type,
        "latency_ms": round((time.perf_counter() - started_at) * 1000),
    }
    feed_type = candidate.get("feed_type")
    if feed_type in {"rss", "atom"}:
        try:
            root = ET.fromstring(content)
            root_name = root.tag.rsplit("}", 1)[-1].lower()
        except ET.ParseError:
            result.update(status="invalid_feed", detail="Response is not parseable RSS or Atom XML.")
            return result
        if root_name not in {"rss", "feed"}:
            result.update(status="invalid_feed", detail=f"Unexpected XML root: {root_name}")
            return result
        result.update(
            status="reachable_paid_headline_only" if candidate.get("license_status") == "paid" else "reachable",
            detail=f"Valid {root_name.upper()} feed. Candidate remains inactive pending approval.",
        )
        return result

    if content_type == "text/html" or b"<html" in content.lower():
        result.update(status="reachable_needs_adapter", detail="Structured page is reachable; no adapter was activated.")
        return result
    result.update(status="invalid_structured_feed", detail="Expected an HTML structured page.")
    return result


def render_report(candidates, results):
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Candidate Source Access Test",
        "",
        f"Tested: {generated_at}",
        "",
        "Every candidate below remains inactive. `paid` candidates are governed by the headline/time/URL-only rule.",
        "",
        "| Candidate | Region | Tier | License | Result | HTTP | Type | Latency |",
        "| --- | --- | ---: | --- | --- | ---: | --- | ---: |",
    ]
    for candidate in candidates:
        result = results[candidate["name"]]
        lines.append(
            f"| {candidate['name']} | {candidate['region']} | {candidate['tier']} | "
            f"{candidate['license_status']} | {result['status']} | {result['http_status']} | "
            f"{result['content_type']} | {result['latency_ms']} ms |"
        )
    lines.extend(["", "## Detail", ""])
    for candidate in candidates:
        result = results[candidate["name"]]
        lines.append(f"- **{candidate['name']}** — {result['detail']}")
    return "\n".join(lines) + "\n"


def main():
    report_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_REPORT_PATH
    candidates = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))["candidates"]
    results = {}
    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="candidate-feed") as executor:
        futures = {executor.submit(probe_candidate, candidate): candidate for candidate in candidates}
        for future in as_completed(futures):
            candidate = futures[future]
            try:
                results[candidate["name"]] = future.result()
            except Exception as error:
                results[candidate["name"]] = {
                    "status": "unreachable",
                    "http_status": "-",
                    "content_type": "-",
                    "latency_ms": "-",
                    "detail": type(error).__name__,
                }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(candidates, results), encoding="utf-8")
    print(f"Candidate report: {report_path}")
    for candidate in candidates:
        print(f"{candidate['name']}: {results[candidate['name']]['status']}")


if __name__ == "__main__":
    main()
