import copy
import json
import sys
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer

import pytest

from api import _engine, briefing_store, story_lifecycle
from api.briefing import handler as briefing_handler
from scripts import run_pipeline

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)
V2 = story_lifecycle.load_relevance_config("v2")
LEVELS = V2["levels"]
SELECTION = V2["selection"]


def story(score, name=None, url=None, narrative="pending"):
    name = name or f"Story scoring {score}"
    url = url or f"https://example.com/{abs(hash(name))}"
    story_id = story_lifecycle.stable_story_id(url)
    return {
        "id": story_id, "story_id": story_id, "section": "Route news", "region_section": "Europe", "headline": name,
        "event_type": None, "relevance_score": score, "narrative_status": narrative, "lead": "l",
        "original_source": {"url": url, "title": f"{name} unique{abs(hash(name)) % 10**6}", "source_name": "Wire"},
        "sources": [{"name": "Wire", "url": url, "title": f"{name} unique{abs(hash(name)) % 10**6}"}], "source_count": 1,
        "published_at_iso": story_lifecycle.to_iso(NOW - HOUR),
    }


# --- the bands ---------------------------------------------------------------------------------------------

def test_the_bands_and_the_thresholds_come_from_the_config():
    assert SELECTION["min_score"] == 40 and SELECTION["archive_min_score"] == 35
    assert [(level["name"], level["label"], level["min_score"], level["listed"]) for level in LEVELS] == [
        ("critical", "Kritik", 60, True), ("important", "Önemli", 45, True), ("watch", "İzle", 40, True), ("low", "Arşiv", 35, False),
    ]


@pytest.mark.parametrize("score, name", [
    (100, "critical"), (60, "critical"), (59.9, "important"), (45, "important"), (44.9, "watch"),
    (40, "watch"), (39.9, "low"), (35, "low"), (34.9, None), (0, None),
])
def test_score_bands(score, name):
    level = story_lifecycle.level_for(score, LEVELS)
    assert (level["name"] if level else None) == name


def test_the_lowest_listed_band_matches_the_selection_threshold():
    assert min(level["min_score"] for level in LEVELS if level["listed"]) == SELECTION["min_score"]


# --- selection --------------------------------------------------------------------------------------------------

def test_stories_between_35_and_40_are_archived_but_not_listed_and_lower_ones_are_dropped():
    stories = [story(score) for score in (70, 50, 42, 39.9, 36, 35, 34.9, 10)]
    chosen = story_lifecycle.select_stories(stories, SELECTION)
    assert sorted(item["relevance_score"] for item in chosen) == [35, 36, 39.9, 42, 50, 70]


def test_the_low_band_has_its_own_cap_so_it_cannot_crowd_out_the_list():
    stories = [story(80 - index, f"Listed {index} alpha{index}") for index in range(4)] + [story(36 + index / 100, f"Low {index} beta{index}") for index in range(30)]
    chosen = story_lifecycle.select_stories(stories, {**SELECTION, "max_per_run": 3, "max_low_per_run": 5})
    scores = [item["relevance_score"] for item in chosen]
    assert len([s for s in scores if s >= 40]) == 3 and len([s for s in scores if s < 40]) == 5


def test_present_stories_labels_every_story_with_its_band():
    day = {"stories": [dict(story(75, "A"), first_seen_at=story_lifecycle.to_iso(NOW)), dict(story(47, "B"), first_seen_at=story_lifecycle.to_iso(NOW)),
                       dict(story(41, "C"), first_seen_at=story_lifecycle.to_iso(NOW)), dict(story(37, "D"), first_seen_at=story_lifecycle.to_iso(NOW)),
                       dict(story(20, "E"), first_seen_at=story_lifecycle.to_iso(NOW))]}
    story_lifecycle.present_stories(day, NOW, levels=LEVELS)
    by_name = {item["headline"]: item for item in day["stories"]}
    assert [(by_name[n]["level"], by_name[n]["level_label"], by_name[n]["listed"]) for n in "ABCDE"] == [
        ("critical", "Kritik", True), ("important", "Önemli", True), ("watch", "İzle", True), ("low", "Arşiv", False), ("below", "", False),
    ]


# --- the API --------------------------------------------------------------------------------------------------------

def day_file(*stories):
    return story_lifecycle.build_day(None, None, {"daily": {"status": "ok", "stories": [copy.deepcopy(s) for s in stories], "market": {}}}, NOW)


def serve(monkeypatch, day):
    files = {briefing_store.latest_path(): day}
    monkeypatch.setattr(briefing_store, "read_json", lambda path: copy.deepcopy(files.get(path)))
    monkeypatch.setattr(story_lifecycle, "utc_now", lambda: NOW)


def test_the_api_lists_only_listed_stories_and_reports_how_many_it_hid(monkeypatch):
    day = day_file(story(70, "Alpha critical"), story(50, "Bravo important"), story(41, "Charlie watch"), story(37, "Delta low"), story(36, "Echo low"))
    assert len(day["stories"]) == 5, "the archive file keeps the low band"
    serve(monkeypatch, day)

    result = _engine.get_ready_briefing("daily")

    assert [item["level"] for item in result["stories"]] == ["critical", "important", "watch"]
    assert result["hidden_low_count"] == 2


def test_include_low_returns_the_archive_only_stories_too(monkeypatch):
    day = day_file(story(70, "Alpha critical"), story(37, "Delta low"))
    serve(monkeypatch, day)

    result = _engine.get_ready_briefing("daily", include_low=True)

    assert sorted(item["level"] for item in result["stories"]) == ["critical", "low"]
    assert result["hidden_low_count"] == 0
    assert all(item["level_label"] for item in result["stories"])


def test_a_past_day_follows_the_same_rule(monkeypatch):
    day = day_file(story(70, "Alpha critical"), story(37, "Delta low"))
    files = {briefing_store.day_path("2026-10-15"): day}
    monkeypatch.setattr(briefing_store, "read_json", lambda path: copy.deepcopy(files.get(path)))
    monkeypatch.setattr(story_lifecycle, "utc_now", lambda: NOW)
    assert len(_engine.get_ready_briefing("daily", date="2026-10-15")["stories"]) == 1
    assert len(_engine.get_ready_briefing("daily", date="2026-10-15", include_low=True)["stories"]) == 2


def test_the_hourly_view_never_shows_the_low_band(monkeypatch):
    serve(monkeypatch, day_file(story(70, "Alpha critical"), story(37, "Delta low")))
    hourly = _engine.get_ready_briefing("hourly", include_low=False)
    assert [item["level"] for item in hourly["stories"]] == ["critical"]


@pytest.mark.parametrize("value, expected", [("1", True), ("true", True), ("yes", True), ("0", False), ("", False), ("no", False)])
def test_include_low_query_parsing(value, expected):
    assert _engine.wants_low({"include_low": [value]}) is expected
    assert _engine.wants_low({}) is False


@pytest.fixture
def api_server():
    server = HTTPServer(("127.0.0.1", 0), briefing_handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_http_endpoint_honours_include_low(api_server, monkeypatch):
    day = day_file(story(70, "Alpha critical"), story(37, "Delta low"))
    files = {briefing_store.latest_path(): day}
    # The Vercel handler imports its modules without the "api." prefix, so it holds separate copies.
    monkeypatch.setattr(sys.modules["briefing_store"], "read_json", lambda path: copy.deepcopy(files.get(path)))
    monkeypatch.setattr(sys.modules["story_lifecycle"], "utc_now", lambda: NOW)

    def count(query):
        with urllib.request.urlopen(f"{api_server}/api/briefing?{query}", timeout=10) as response:
            return len(json.loads(response.read().decode("utf-8"))["stories"])

    assert count("mode=daily") == 1
    assert count("mode=daily&include_low=1") == 2


# --- the pipeline ---------------------------------------------------------------------------------------------------

def collected(*stories):
    return {"stories": [copy.deepcopy(s) for s in stories], "articles": 100, "candidates": len(stories), "market": {"status": "ok", "items": [], "events": []}}


def test_the_low_band_is_archived_without_spending_any_llm_call(tmp_path, monkeypatch):
    monkeypatch.setattr(_engine, "collect_run", lambda: collected(story(70, "Alpha critical"), story(37, "Delta low"), story(36, "Echo low")))
    seen = []

    def spy(stories, api_key, description_limit, now=None):
        seen.append([item["headline"] for item in stories])
        return {"calls": 1, "narrated": 0, "pending": len(stories), "error": ""}

    assert run_pipeline.run(out_dir=tmp_path, now=NOW, api_key="k", narrate=spy) == 0

    assert seen == [["Alpha critical"]]
    day = json.loads((tmp_path / "briefings/2026-10-16.json").read_text(encoding="utf-8"))
    assert {item["headline"] for item in day["stories"]} == {"Alpha critical", "Delta low", "Echo low"}
    assert json.loads((tmp_path / "briefings/status.json").read_text(encoding="utf-8"))["narrative_pending"] == 1


def test_a_low_story_that_reaches_the_list_is_narrated_then(tmp_path, monkeypatch):
    low = story(37, "Delta low")
    monkeypatch.setattr(_engine, "collect_run", lambda: collected(low))
    narrated = []

    def narrate(stories, api_key, description_limit, now=None):
        narrated.append([item["headline"] for item in stories])
        for item in stories:
            item["narrative_status"] = "done"
        return {"calls": 1 if stories else 0, "narrated": len(stories), "pending": 0, "error": ""}

    run_pipeline.run(out_dir=tmp_path, now=NOW, api_key="k", narrate=narrate)
    promoted = dict(low, relevance_score=52.0)
    monkeypatch.setattr(_engine, "collect_run", lambda: collected(promoted))
    run_pipeline.run(out_dir=tmp_path, now=NOW + HOUR, api_key="k", narrate=narrate)

    assert narrated == [[], ["Delta low"]]
