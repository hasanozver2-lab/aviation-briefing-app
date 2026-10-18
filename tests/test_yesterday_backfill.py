import copy
from datetime import datetime, timedelta, timezone

import pytest

from api import _engine, briefing_store, story_lifecycle

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
TODAY, YESTERDAY = "2026-10-16", "2026-10-15"


def story(name, score=70, hours_ago=1):
    url = f"https://example.com/{name.replace(' ', '-').lower()}"
    story_id = story_lifecycle.stable_story_id(url)
    seen = story_lifecycle.to_iso(NOW - timedelta(hours=hours_ago))
    return {
        "id": story_id, "story_id": story_id, "headline": name, "event_type": "route_network_change",
        "relevance_score": score, "narrative_status": "done", "lead": "l", "why_it_matters": "w",
        "region_section": "Europe", "section": "Route news", "source_count": 1,
        "entities": {"carriers": [], "groups": []}, "first_seen_at": seen, "last_updated_at": seen,
        "published_at_iso": seen, "previous_score": None,
        "original_source": {"url": url, "title": name, "source_name": "Wire", "tier": 2, "official": False},
        "sources": [{"name": "Wire", "url": url, "title": name}],
    }


def day(date, *stories):
    return {"date": date, "status": "ok", "stories": [copy.deepcopy(item) for item in stories], "market": {},
            "mode": "daily", "last_pipeline_run_at": story_lifecycle.to_iso(NOW)}


@pytest.fixture
def serve(monkeypatch):
    def _serve(today, yesterday=None):
        files = {briefing_store.latest_path(): today, briefing_store.day_path(YESTERDAY): yesterday}
        monkeypatch.setattr(briefing_store, "read_json", lambda path: copy.deepcopy(files.get(path)))
        monkeypatch.setattr(story_lifecycle, "utc_now", lambda: NOW)
    return _serve


def test_a_thin_current_day_never_includes_previous_day_stories(serve):
    serve(day(TODAY, story("Today A")), day(YESTERDAY, story("Old A", 99), story("Old B", 98)))

    result = _engine.get_ready_briefing("daily")

    assert [item["headline"] for item in result["stories"]] == ["Today A"]
    assert result["yesterday_count"] == 0


def test_old_publications_in_todays_archive_are_hidden_without_replacement(serve):
    delayed = story("Delayed feed item", 95)
    delayed["published_at_iso"] = story_lifecycle.to_iso(NOW - timedelta(days=1))
    delayed["first_seen_at"] = story_lifecycle.to_iso(NOW - timedelta(hours=1))
    serve(day(TODAY, story("Today only"), delayed), day(YESTERDAY, story("Old", 99)))

    result = _engine.get_ready_briefing("daily")

    assert [item["headline"] for item in result["stories"]] == ["Today only"]
    assert result["older_archive_count"] == 1
    assert result["yesterday_count"] == 0


def test_current_day_filter_uses_the_istanbul_calendar():
    at_local_midnight = story("Istanbul midnight")
    at_local_midnight["published_at_iso"] = "2026-10-15T21:30:00+00:00"
    assert story_lifecycle.published_on_day(at_local_midnight, TODAY, story_lifecycle.load_badges_config())


def test_explicit_date_keeps_the_requested_archive(monkeypatch):
    archive = day(YESTERDAY, story("Archived story", hours_ago=25))
    files = {briefing_store.day_path(YESTERDAY): archive}
    monkeypatch.setattr(briefing_store, "read_json", lambda path: copy.deepcopy(files.get(path)))
    monkeypatch.setattr(story_lifecycle, "utc_now", lambda: NOW)

    result = _engine.get_ready_briefing("daily", date=YESTERDAY)

    assert [item["headline"] for item in result["stories"]] == ["Archived story"]
    assert result["yesterday_count"] == 0


def test_the_default_request_is_the_daily_view():
    from api import briefing
    source = open(briefing.__file__, encoding="utf-8").read()
    assert 'query.get("mode", ["daily"])' in source
