import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from api import _engine, briefing_store, blob_store, github_store, market_data

PROJECT_DIR = Path(__file__).resolve().parents[1]


def git(directory, *args):
    result = subprocess.run(["git", *args], cwd=directory, capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture
def remote_and_work(tmp_path):
    """A bare 'origin' plus a work clone whose main branch must never be modified by publishing."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    git(tmp_path, "init", "-b", "main", str(work))
    git(work, "config", "user.name", "dev")
    git(work, "config", "user.email", "dev@example.com")
    (work / "app.txt").write_text("app", encoding="utf-8")
    git(work, "add", "app.txt")
    git(work, "commit", "-m", "app")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-q", "origin", "main")
    return origin, work


def read_branch_file(origin, path, branch="briefing-data"):
    return json.loads(git(origin, "show", f"{branch}:{path}"))


# --- publishing to the data branch -------------------------------------------------

def test_publish_creates_the_data_branch_without_touching_main(remote_and_work):
    origin, work = remote_and_work
    main_before = git(origin, "rev-parse", "main")

    commit = github_store.publish_files(
        {"briefings/daily.json": {"mode": "daily", "n": 1}, "briefings/daily-status.json": {"status": "ok"}},
        "Publish briefings test", repo_dir=work,
    )

    assert commit and git(origin, "rev-parse", "briefing-data") == commit
    assert git(origin, "rev-parse", "main") == main_before            # main is never written
    assert sorted(git(origin, "for-each-ref", "--format=%(refname)").splitlines()) == ["refs/heads/briefing-data", "refs/heads/main"]
    assert read_branch_file(origin, "briefings/daily.json") == {"mode": "daily", "n": 1}
    assert git(origin, "log", "-1", "--format=%an", "briefing-data") == "aerobrief-bot"
    assert git(work, "rev-parse", "--abbrev-ref", "HEAD") == "main"    # checkout and working tree untouched
    assert git(work, "status", "--porcelain") == ""


def test_both_modes_land_in_one_commit_and_earlier_files_are_kept(remote_and_work):
    origin, work = remote_and_work
    files = {
        "briefings/daily.json": {"mode": "daily"}, "briefings/hourly.json": {"mode": "hourly"},
        "briefings/daily-status.json": {"status": "ok"}, "briefings/hourly-status.json": {"status": "ok"},
    }
    github_store.publish_files(files, "first", repo_dir=work)
    github_store.publish_files({"briefings/hourly.json": {"mode": "hourly", "n": 2}}, "second", repo_dir=work)

    assert git(origin, "rev-list", "--count", "briefing-data") == "2"
    assert read_branch_file(origin, "briefings/hourly.json")["n"] == 2
    assert read_branch_file(origin, "briefings/daily.json") == {"mode": "daily"}   # preserved
    first = git(origin, "log", "--format=%H", "--reverse", "briefing-data").splitlines()[0]
    tree = git(origin, "ls-tree", "-r", "--name-only", first).splitlines()
    assert sorted(tree) == ["briefings/daily-status.json", "briefings/daily.json", "briefings/hourly-status.json", "briefings/hourly.json", "vercel.json"]


def test_unchanged_content_makes_no_commit(remote_and_work):
    origin, work = remote_and_work
    github_store.publish_files({"briefings/daily.json": {"a": 1}}, "first", repo_dir=work)
    assert github_store.publish_files({"briefings/daily.json": {"a": 1}}, "again", repo_dir=work) == ""
    assert git(origin, "rev-list", "--count", "briefing-data") == "1"


def test_the_data_branch_disables_vercel_deployments_for_itself(remote_and_work):
    origin, work = remote_and_work
    github_store.publish_files({"briefings/daily.json": {}}, "x", repo_dir=work)
    config = read_branch_file(origin, "vercel.json")
    assert config["git"]["deploymentEnabled"] == {"briefing-data": False}


def test_publish_rejects_paths_that_escape_the_store(remote_and_work):
    _, work = remote_and_work
    with pytest.raises(ValueError):
        github_store.publish_files({"../evil.json": {}}, "x", repo_dir=work)


def test_files_can_be_removed_from_the_data_branch_in_the_same_commit(remote_and_work):
    origin, work = remote_and_work
    github_store.publish_files({"briefings/daily.json": {"old": True}, "briefings/latest.json": {"v": 1}}, "first", repo_dir=work)

    github_store.publish_files({"briefings/latest.json": {"v": 2}}, "cleanup", repo_dir=work, remove=["briefings/daily.json", "briefings/never-existed.json"])

    names = git(origin, "ls-tree", "-r", "--name-only", "briefing-data").splitlines()
    assert sorted(names) == ["briefings/latest.json", "vercel.json"]
    assert read_branch_file(origin, "briefings/latest.json") == {"v": 2}
    assert git(origin, "rev-list", "--count", "briefing-data") == "2"      # history keeps the old files


# --- reading ------------------------------------------------------------------------

def test_default_read_url_points_at_the_data_branch(monkeypatch):
    for name in ("BRIEFING_DATA_REPO", "BRIEFING_DATA_BRANCH", "VERCEL_GIT_REPO_OWNER", "VERCEL_GIT_REPO_SLUG"):
        monkeypatch.delenv(name, raising=False)
    assert github_store.public_url("briefings/daily.json") == (
        "https://raw.githubusercontent.com/hasanozver2-lab/aviation-briefing-app/briefing-data/briefings/daily.json"
    )


def test_read_location_can_be_overridden_by_environment(monkeypatch):
    monkeypatch.setenv("BRIEFING_DATA_REPO", "me/other")
    monkeypatch.setenv("BRIEFING_DATA_BRANCH", "data")
    assert github_store.public_url("briefings/hourly.json") == "https://raw.githubusercontent.com/me/other/data/briefings/hourly.json"


def test_vercel_system_variables_locate_the_repository(monkeypatch):
    monkeypatch.delenv("BRIEFING_DATA_REPO", raising=False)
    monkeypatch.setenv("VERCEL_GIT_REPO_OWNER", "owner")
    monkeypatch.setenv("VERCEL_GIT_REPO_SLUG", "repo")
    assert github_store.repo_slug() == "owner/repo"


def test_unreadable_store_returns_none_instead_of_raising(monkeypatch):
    def failing(*_args, **_kwargs):
        raise OSError("network down")
    monkeypatch.setattr(github_store.urllib.request, "urlopen", failing)
    assert github_store.get_public_json("briefings/daily.json") is None


# --- store selection ----------------------------------------------------------------

def test_github_is_the_default_store(monkeypatch):
    monkeypatch.delenv("BRIEFING_STORE", raising=False)
    assert briefing_store.selected_store() == "github"


def test_blob_store_stays_selectable_by_environment(monkeypatch):
    calls = []
    monkeypatch.setenv("BRIEFING_STORE", "blob")
    monkeypatch.setattr(blob_store, "get_public_json", lambda path: calls.append(("read", path)) or {"ok": True})
    monkeypatch.setattr(blob_store, "put_public_json", lambda path, payload: calls.append(("write", path)))

    assert briefing_store.read_json("briefings/daily.json") == {"ok": True}
    briefing_store.publish({"briefings/daily.json": {}}, "msg")
    assert calls == [("read", "briefings/daily.json"), ("write", "briefings/daily.json")]


def test_invalid_store_name_is_rejected(monkeypatch):
    monkeypatch.setenv("BRIEFING_STORE", "s3")
    with pytest.raises(ValueError, match="BRIEFING_STORE"):
        briefing_store.selected_store()


# --- fallback to the committed cache --------------------------------------------------

def test_unreadable_store_falls_back_to_the_committed_cache_as_stale(tmp_path, monkeypatch):
    cache = tmp_path / "briefing_cache_daily.json"
    cache.write_text(json.dumps({"mode": "daily", "generated_at": "2026-10-14T13:33:39", "stories": [{"id": "old"}]}), encoding="utf-8")
    monkeypatch.setattr(_engine, "CACHE_FILE_DAILY", cache)
    monkeypatch.setattr(briefing_store, "read_json", lambda path: None)

    result = _engine.get_ready_briefing("daily")

    assert result["status"] == "stale"
    assert result["stories"] == [{"id": "old"}]
    assert result["last_pipeline_run_at"] == "2026-10-14T13:33:39"
    assert "could not be read" in result["warning"]


def test_readable_store_wins_over_the_committed_cache(tmp_path, monkeypatch):
    cache = tmp_path / "briefing_cache_daily.json"
    cache.write_text(json.dumps({"mode": "daily", "stories": [{"id": "old"}]}), encoding="utf-8")
    monkeypatch.setattr(_engine, "CACHE_FILE_DAILY", cache)
    live = {"mode": "daily", "status": "ok", "generated_at": "2026-10-16T09:00:00+00:00", "stories": [{"id": "live"}]}
    monkeypatch.setattr(briefing_store, "read_json", lambda path: live if path.endswith("latest.json") else {"status": "ok"})

    result = _engine.get_ready_briefing("daily")

    assert result["status"] == "ok" and result["stories"] == [{"id": "live"}]


# --- optional EIA key (FRED fallback is covered in test_fred_market.py) -----------------------------------------------------------------

def test_missing_eia_key_skips_fuel_but_ecb_rates_continue(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "fetch_eia_series", lambda *a, **k: (_ for _ in ()).throw(AssertionError("EIA must not be called")))
    today = date(2026, 10, 15)
    monkeypatch.setattr(market_data, "fetch_fred_series", lambda *a, **k: (_ for _ in ()).throw(OSError("FRED unreachable")))
    monkeypatch.setattr(market_data, "fetch_ecb_fx_series", lambda start, end: {"fx_usd_try": [(today - timedelta(days=1), 40.0), (today, 41.0)]})

    monkeypatch.setattr(market_data, "display_fx", lambda: True)
    panel = market_data.refresh_market_data(tmp_path / "m.sqlite3", eia_api_key="", end_date=today)

    assert panel["skipped"] == ["EIA"] and panel["errors"] == ["FRED: OSError"]
    assert panel["status"] == "partial"
    assert "EIA" in panel["missing_data_note"]
    assert [item["series_id"] for item in panel["items"]] == ["fx_usd_try"]


def test_present_eia_key_keeps_the_panel_complete(tmp_path, monkeypatch):
    rows = [(date(2026, 10, 14), 80.0), (date(2026, 10, 15), 81.0)]
    monkeypatch.setattr(market_data, "fetch_eia_series", lambda *a, **k: rows)
    monkeypatch.setattr(market_data, "fetch_ecb_fx_series", lambda start, end: {})
    panel = market_data.refresh_market_data(tmp_path / "m.sqlite3", eia_api_key="key", end_date=date(2026, 10, 15))
    assert panel["skipped"] == [] and "missing_data_note" not in panel


# --- repository configuration ---------------------------------------------------------

def test_vercel_config_disables_deployments_for_the_data_branch():
    config = json.loads((PROJECT_DIR / "vercel.json").read_text(encoding="utf-8"))
    assert config["git"]["deploymentEnabled"] == {github_store.DEFAULT_BRANCH: False}
    assert github_store.VERCEL_CONFIG["git"]["deploymentEnabled"] == {github_store.DEFAULT_BRANCH: False}


def test_workflow_is_one_scheduled_job_with_only_contents_write():
    workflow = (PROJECT_DIR / ".github" / "workflows" / "briefing-pipeline.yml").read_text(encoding="utf-8")
    code = "\n".join(line for line in workflow.splitlines() if not line.lstrip().startswith("#"))
    assert code.count("cron:") == 1 and 'cron: "7,22,37,52 * * * *"' in code
    assert "permissions:\n  contents: write" in code
    assert code.count("permissions:") == 1
    assert code.count("jobs:\n  publish:") == 1 and code.count("runs-on:") == 1
    assert "BRIEFING_STORE: github" in code
    assert "BLOB_" not in code
    assert "git push" not in code                      # pushing is done by the script, to the data branch only
    assert "aerobrief-publish" in code and "cancel-in-progress: false" in code
