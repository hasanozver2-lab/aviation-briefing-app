import copy
from datetime import datetime, timedelta, timezone

import pytest

from api import _engine, briefing_store, story_lifecycle

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
TODAY, YESTERDAY = "2026-10-16", "2026-10-15"
MINIMUM = story_lifecycle.load_badges_config()["daily_min_stories"]


def story(name, score, hours_ago=1, event_type="route_network_change", tier=2):
    url = f"https://example.com/{name.replace(' ', '-').lower()}"
    story_id = story_lifecycle.stable_story_id(url)
    seen = story_lifecycle.to_iso(NOW - timedelta(hours=hours_ago))
    return {
        "id": story_id, "story_id": story_id, "headline": name, "event_type": event_type, "relevance_score": score, "narrative_status": "done",
        "lead": "l", "why_it_matters": "w", "region_section": "Europe", "section": "Route news", "source_count": 1, "entities": {"carriers": [], "groups": []},
        "first_seen_at": seen, "last_updated_at": seen, "published_at_iso": seen, "previous_score": None,
        "original_source": {"url": url, "title": name, "source_name": "Wire", "tier": tier, "official": False},
        "sources": [{"name": "Wire", "url": url, "title": name}],
    }


def day(date, *stories):
    return {"date": date, "status": "ok", "stories": [copy.deepcopy(s) for s in stories], "market": {}, "mode": "daily",
            "last_pipeline_run_at": story_lifecycle.to_iso(NOW)}


@pytest.fixture
def serve(monkeypatch):
    def _serve(today, yesterday=None):
        files = {briefing_store.latest_path(): today, briefing_store.day_path(YESTERDAY): yesterday}
        monkeypatch.setattr(briefing_store, "read_json", lambda path: copy.deepcopy(files.get(path)))
        monkeypatch.setattr(story_lifecycle, "utc_now", lambda: NOW)
    return _serve


def headlines(result, carried):
    return [item["headline"] for item in result["stories"] if bool(item.get("carried_from")) is carried]


def test_a_thin_day_is_topped_up_to_the_minimum_with_yesterdays_best_stories(serve):
    today = day(TODAY, story("Today A", 70), story("Today B", 55))
    yesterday = day(YESTERDAY, *[story(f"Old {index}", 80 - index) for index in range(10)])
    serve(today, yesterday)

    result = _engine.get_ready_briefing("daily")

    assert len(result["stories"]) == MINIMUM
    assert headlines(result, False) == ["Today A", "Today B"]
    assert headlines(result, True) == [f"Old {index}" for index in range(MINIMUM - 2)]       # the highest scores, best first
    assert result["yesterday_count"] == MINIMUM - 2


def test_yesterdays_stories_carry_no_badges_so_they_are_never_breaking_or_new(serve):
    fresh = story("Fresh disruption", 90, hours_ago=1, event_type="safety_incident")
    serve(day(TODAY, story("Today A", 70)), day(YESTERDAY, fresh))     # first seen an hour ago: a normal story would be New and Breaking

    result = _engine.get_ready_briefing("daily")

    carried = [item for item in result["stories"] if item.get("carried_from")]
    assert [item["headline"] for item in carried] == ["Fresh disruption"]
    assert carried[0]["carried_from"] == "yesterday" and carried[0]["badges"] == []


def test_no_backfill_when_today_already_has_enough(serve):
    today = day(TODAY, *[story(f"Today {index}", 70 - index) for index in range(MINIMUM)])
    serve(today, day(YESTERDAY, story("Old", 99)))
    result = _engine.get_ready_briefing("daily")
    assert headlines(result, True) == [] and result["yesterday_count"] == 0


def test_a_story_already_shown_today_is_not_repeated_from_yesterday(serve):
    repeat = story("Same story", 80)
    serve(day(TODAY, repeat), day(YESTERDAY, repeat, story("Different", 60)))
    result = _engine.get_ready_briefing("daily")
    assert [item["headline"] for item in result["stories"]].count("Same story") == 1
    assert "Different" in headlines(result, True)


def test_yesterdays_excluded_and_low_scoring_stories_are_not_carried_over(serve):
    stock = story("Airline stock drops on analyst downgrade", 90, event_type="capital_markets", tier=3)
    low = story("Low band", 37)
    serve(day(TODAY, story("Today A", 70)), day(YESTERDAY, stock, low, story("Good one", 62)))
    assert headlines(_engine.get_ready_briefing("daily"), True) == ["Good one"]


def test_no_previous_day_means_no_backfill_and_no_error(serve):
    serve(day(TODAY, story("Today A", 70)), None)
    result = _engine.get_ready_briefing("daily")
    assert len(result["stories"]) == 1 and result["yesterday_count"] == 0


def test_the_backfill_never_rewrites_the_archive_file(serve):
    today = day(TODAY, story("Today A", 70))
    yesterday = day(YESTERDAY, story("Old", 60))
    serve(today, yesterday)
    _engine.get_ready_briefing("daily")
    assert len(today["stories"]) == 1 and "carried_from" not in yesterday["stories"][0]


def test_an_explicit_date_and_the_live_view_are_left_alone(serve, monkeypatch):
    serve(day(TODAY, story("Today A", 70)), day(YESTERDAY, story("Old", 60)))
    assert headlines(_engine.get_ready_briefing("hourly"), True) == []
    files = {briefing_store.day_path(TODAY): day(TODAY, story("Today A", 70)), briefing_store.day_path(YESTERDAY): day(YESTERDAY, story("Old", 60))}
    monkeypatch.setattr(briefing_store, "read_json", lambda path: copy.deepcopy(files.get(path)))
    assert headlines(_engine.get_ready_briefing("daily", date=TODAY), True) == []


def test_the_default_request_is_the_daily_view():
    from api import briefing
    source = open(briefing.__file__, encoding="utf-8").read()
    assert 'query.get("mode", ["daily"])' in source
