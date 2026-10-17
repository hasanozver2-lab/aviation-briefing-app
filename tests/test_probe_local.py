import hashlib
import json
from pathlib import Path

from api import source_catalog, source_probe
from scripts import probe_local

PROJECT = Path(__file__).resolve().parents[1]


def record(name, status, **extra):
    base = {"name": name, "source_type": "airline_ir", "status": status, "reason": "" if status == "active" else "HTTPError 403", "method": "rss" if status == "active" else "", "http_code": 200,
            "seconds": 0.5, "items_7d": 1, "items_90d": 3, "robots": "read"}
    base.update(extra)
    return base


LOCAL = [record("Both", "active"), record("Only Local", "active"), record("Only Runner", "disabled_blocked"), record("Neither", "disabled_blocked"), record("New", "active")]
RUNNER = [record("Both", "active"), record("Only Local", "disabled_blocked"), record("Only Runner", "active"), record("Neither", "disabled_blocked")]


def test_comparison_names_the_sources_that_open_only_from_one_network():
    groups = probe_local.compare(LOCAL, RUNNER)
    assert groups == {"only_local": ["Only Local"], "only_runner": ["Only Runner"], "both": ["Both"], "neither": ["Neither"], "not_in_runner_probe": ["New"]}


def test_the_summary_lists_the_sources_open_only_from_your_network():
    lines = probe_local.summary_lines(probe_local.compare(LOCAL, RUNNER), LOCAL, RUNNER)
    text = "\n".join(lines)
    assert "open from both: 1" in text and "only from this computer: 1" in text and "Open only from your network" in text and "Only Local" in text


def test_running_the_script_writes_only_its_report_and_touches_nothing_else(tmp_path, monkeypatch):
    catalog_before = hashlib.sha256(source_catalog.SOURCES_CSV_PATH.read_bytes()).hexdigest()
    runner_file = tmp_path / "runner.json"
    runner_file.write_text(json.dumps({"sources": RUNNER}), encoding="utf-8")
    monkeypatch.setattr(source_probe, "probe_all", lambda rows, builtin, discovered, now, legacy_fetch=None, workers=8: ([dict(r) for r in LOCAL], []))
    out = tmp_path / "out" / "probe_local.json"
    assert probe_local.main(["--out", str(out), "--runner", str(runner_file), "--only", "Delta News Hub"]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert [r["name"] for r in report["sources"]] == [r["name"] for r in LOCAL] and report["comparison"]["only_local"] == ["Only Local"]
    assert report["user_agent"].startswith("Mozilla/5.0 (compatible; aviation-briefing-app/1.0") and report["python"]
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["probe_local.json", "runner.json"]
    assert hashlib.sha256(source_catalog.SOURCES_CSV_PATH.read_bytes()).hexdigest() == catalog_before


def test_the_script_has_no_way_to_write_to_the_data_branch_the_archive_or_secrets():
    code = (PROJECT / "scripts" / "probe_local.py").read_text(encoding="utf-8")
    for forbidden in ("briefing_store", "github_store", "publish", "status_path", "GEMINI", "getenv", "environ", ".env", "git push"):
        assert forbidden not in code, forbidden


def test_without_a_runner_file_it_still_writes_the_report(tmp_path, monkeypatch):
    monkeypatch.setattr(source_probe, "probe_all", lambda rows, builtin, discovered, now, legacy_fetch=None, workers=8: ([dict(r) for r in LOCAL], []))
    out = tmp_path / "p.json"
    assert probe_local.main(["--out", str(out), "--runner", str(tmp_path / "missing.json"), "--only", "Delta News Hub"]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["comparison"] == {}


def test_readme_documents_the_command_python_version_and_packages():
    readme = (PROJECT / "README.md").read_text(encoding="utf-8")
    assert "python scripts/probe_local.py" in readme and "Python 3.11" in readme and "requirements.txt" in readme
    assert "standart kütüphane" in (PROJECT / "README.md").read_text(encoding="utf-8").lower() or "standard library" in readme.lower()
