import copy
import json

import pytest

from scripts import build_pages


class Snapshots:
    commit = "test-immutable-commit"
    paths = ["briefings/latest.json", "briefings/2026-10-22.json", "briefings/status.json"]

    def __init__(self):
        self.payloads = {
            "briefings/latest.json": {"date": "2026-10-22", "stories": []},
            "briefings/2026-10-22.json": {"date": "2026-10-22", "stories": []},
            "briefings/status.json": {"status": "stale"},
        }

    def __call__(self, path):
        return copy.deepcopy(self.payloads.get(path))


def test_pages_uses_same_ready_presenter_and_exports_archive_low_band(tmp_path, monkeypatch):
    snapshots = Snapshots()
    calls = []

    def present(**kwargs):
        assert kwargs["reader"] is snapshots
        calls.append(kwargs)
        return {"date": kwargs.get("date", "2026-10-23"), "stories": [], "status": "stale"}

    monkeypatch.setattr(build_pages.engine, "get_ready_briefing", present)
    build_pages.build(tmp_path, snapshots)
    assert len(calls) == 2
    assert calls[1]["include_low"] is True
    assert json.loads((tmp_path / "data/latest.json").read_text())["status"] == "stale"
    assert (tmp_path / "data/2026-10-22.json").is_file()
    assert not (tmp_path / "instagram").exists()


def test_missing_ready_snapshot_fails_before_writing(tmp_path):
    snapshots = Snapshots()
    snapshots.payloads.clear()
    with pytest.raises(ValueError, match="No ready latest snapshot"):
        build_pages.build(tmp_path, snapshots)
    assert list(tmp_path.iterdir()) == []


def test_pages_rewrites_all_three_reads_and_keeps_vercel_source_unchanged():
    original = (build_pages.PUBLIC_DIR / "index.html").read_text(encoding="utf-8")
    html = build_pages.pages_html(original)
    assert html.count("await fetchBriefing(") == 3
    assert 'date ? `data/${date}.json` : "data/latest.json"' in html
    assert 'href="/static/' not in html
    assert 'href="./manifest.json"' in html
    assert "https://fonts.googleapis.com" not in html
    assert "https://fonts.gstatic.com" not in html
    assert (build_pages.PUBLIC_DIR / "index.html").read_text(encoding="utf-8") == original
    assert 'await fetch(`${BRIEFING_URL}' in original


def test_pages_refuses_to_ship_if_ui_transport_changes():
    with pytest.raises(ValueError, match="Expected one application script"):
        build_pages.pages_html("<html></html>")
    with pytest.raises(ValueError, match="briefing requests"):
        build_pages.pages_html("  <script>\n</script>")


def test_pages_manifest_stays_under_project_subpath():
    original = json.loads((build_pages.PUBLIC_DIR / "manifest.json").read_text(encoding="utf-8"))
    manifest = build_pages.pages_manifest(original)
    assert manifest["start_url"] == manifest["scope"] == manifest["id"] == "./"
    assert all(icon["src"].startswith("./static/") for icon in manifest["icons"])
    assert original["start_url"] == "/"


def test_ready_reader_never_reads_the_network(monkeypatch):
    monkeypatch.setattr(build_pages.engine.briefing_store, "read_json", lambda path: pytest.fail("Network store was read"))
    result = build_pages.engine.get_ready_briefing(reader=Snapshots())
    assert result["status"] == "stale"
    assert result["date"] == "2026-10-22"
