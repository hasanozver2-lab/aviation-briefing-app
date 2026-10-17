import copy
import json
from datetime import datetime, timedelta, timezone

from api import _engine, source_catalog
from scripts import run_pipeline

NOW = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)


def story(name, score=70):
    from api import story_lifecycle
    url = f"https://example.com/{name}"
    story_id = story_lifecycle.stable_story_id(url)
    return {"id": story_id, "story_id": story_id, "section": "Route news", "region_section": "Europe", "headline": name, "event_type": None, "relevance_score": score,
            "narrative_status": "pending", "lead": "l", "original_source": {"url": url, "title": name, "source_name": "Wire"},
            "sources": [{"name": "Wire", "url": url, "title": name}], "source_count": 1, "published_at_iso": story_lifecycle.to_iso(NOW - HOUR)}


def collected(source_report):
    return {"stories": [story("Alpha story")], "articles": 50, "candidates": 1, "market": {"status": "ok", "items": [], "events": []}, "source_report": source_report}


def fake_rows(monkeypatch, rows):
    monkeypatch.setattr(source_catalog, "read_rows", lambda path=None: rows)


def row(name, status="active", reason=""):
    return {"name": name, "status": status, "reason": reason}


def test_health_has_status_last_ok_and_articles_in_24_hours(monkeypatch):
    fake_rows(monkeypatch, [row("Quiet Source", "no_public_feed", "no public feed"), row("Good Source"), row("Bad Source")])
    report = {"Good Source": {"status": "active", "error": "", "articles": 3, "articles_24h": 2}, "Bad Source": {"status": "active", "error": "HTTPError 403", "articles": 0}}
    health = run_pipeline.source_health(report, {"sources": {"Bad Source": {"last_ok_at": "2026-10-16T08:00:00+00:00"}}}, NOW)
    assert health["Good Source"] == {"status": "active", "last_ok_at": run_pipeline.timestamp(NOW), "articles_24h": 2, "error": ""}
    assert health["Bad Source"] == {"status": "error", "last_ok_at": "2026-10-16T08:00:00+00:00", "articles_24h": 0, "error": "HTTPError 403"}
    assert health["Quiet Source"]["status"] == "no_public_feed" and health["Quiet Source"]["error"] == "no public feed" and health["Quiet Source"]["last_ok_at"] == ""


def test_a_source_that_answers_with_no_new_items_still_counts_as_read_ok(monkeypatch):
    fake_rows(monkeypatch, [])
    health = run_pipeline.source_health({"Calm": {"status": "active", "error": "", "articles": 0}}, None, NOW)
    assert health["Calm"]["status"] == "active" and health["Calm"]["last_ok_at"] == run_pipeline.timestamp(NOW)


def test_the_summary_counts_unresolved_sources(monkeypatch):
    fake_rows(monkeypatch, [])
    health = run_pipeline.source_health({"A": {"status": "active", "error": "", "articles": 1}, "B": {"status": "disabled_blocked", "error": "403", "articles": 0},
                                         "C": {"status": "active", "error": "TimeoutError", "articles": 0}}, None, NOW)
    assert run_pipeline.source_summary(health) == {"sources": 3, "reading_ok": 1, "unresolved": 2}


def test_many_unresolved_sources_do_not_fail_the_pipeline_and_show_up_in_status_json(tmp_path, monkeypatch):
    fake_rows(monkeypatch, [])
    blocked = {f"Blocked {n}": {"status": "disabled_blocked", "error": "HTTPError 403", "articles": 0} for n in range(30)}
    monkeypatch.setattr(_engine, "collect_run", lambda: collected({**blocked, "Fine": {"status": "active", "error": "", "articles": 5, "articles_24h": 5}}))
    exit_code = run_pipeline.run(out_dir=tmp_path, now=NOW, api_key="", narrate=lambda stories, *a, **k: {"calls": 0, "narrated": 0, "pending": 0, "error": ""})
    status = json.loads((tmp_path / "briefings/status.json").read_text(encoding="utf-8"))
    assert exit_code == 0 and status["status"] == "ok"
    assert status["source_summary"] == {"sources": 31, "reading_ok": 1, "unresolved": 30} and status["sources"]["Fine"]["articles_24h"] == 5


def test_last_ok_survives_across_runs(tmp_path, monkeypatch):
    fake_rows(monkeypatch, [])
    quiet = lambda stories, *a, **k: {"calls": 0, "narrated": 0, "pending": 0, "error": ""}
    monkeypatch.setattr(_engine, "collect_run", lambda: collected({"Flaky": {"status": "active", "error": "", "articles": 1, "articles_24h": 1}}))
    run_pipeline.run(out_dir=tmp_path, now=NOW, api_key="", narrate=quiet)
    monkeypatch.setattr(_engine, "collect_run", lambda: collected({"Flaky": {"status": "active", "error": "TimeoutError", "articles": 0}}))
    run_pipeline.run(out_dir=tmp_path, now=NOW + 4 * HOUR, api_key="", narrate=quiet)
    status = json.loads((tmp_path / "briefings/status.json").read_text(encoding="utf-8"))
    assert status["sources"]["Flaky"]["status"] == "error" and status["sources"]["Flaky"]["last_ok_at"] == run_pipeline.timestamp(NOW)


def payload(sources, at):
    return {"status": "ok", "errors": {}, "narrative_pending": 0, "last_attempt_at": run_pipeline.timestamp(at),
            "sources": {name: {"status": status, "last_ok_at": "", "articles_24h": 0, "error": ""} for name, status in sources.items()}}


def test_status_json_is_rewritten_when_a_source_status_flips_or_the_heartbeat_is_old_but_not_for_timestamps():
    old = payload({"A": "active"}, NOW)
    assert not run_pipeline.status_changed(old, payload({"A": "active"}, NOW + HOUR))
    assert run_pipeline.status_changed(old, payload({"A": "error"}, NOW + HOUR))
    assert run_pipeline.status_changed(old, payload({"A": "active"}, NOW + timedelta(hours=run_pipeline.HEARTBEAT_HOURS)))
