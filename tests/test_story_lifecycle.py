import copy
import json
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer

import pytest

from api import _engine, briefing_store, story_lifecycle
from api.briefing import handler as briefing_handler
from scripts import run_pipeline

UTC = timezone.utc
NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)          # 12:00 in Istanbul
HOUR = timedelta(hours=1)
CONFIG = story_lifecycle.load_badges_config()


def story(url="https://example.com/thy-cfm", headline="THY signs engine deal", score=40.0, publishers=("Wire A",),
          published=NOW - HOUR, title=None, event_type="geopolitics_airspace"):
    sources = [{"name": name, "url": f"{url}?via={index}" if index else url, "title": title or headline} for index, name in enumerate(publishers)]
    story_id = story_lifecycle.stable_story_id(url, headline)
    return {
        "id": story_id, "story_id": story_id, "section": "Route news", "headline": headline, "event_type": event_type,
        "original_source": {"title": title or headline, "source_name": publishers[0], "url": url},
        "relevance_score": score, "sources": sources, "source_count": len(set(publishers)),
        "published_at_iso": story_lifecycle.to_iso(published), "detailed_analysis": ["first analysis"],
    }


def briefing(*stories, mode="daily"):
    return {"mode": mode, "status": "ok", "heading": "Aviation Briefing | 16 October 2026", "intro_sentence": "Intro",
            "stories": [copy.deepcopy(item) for item in stories], "last_pipeline_run_at": story_lifecycle.to_iso(NOW),
            "market": {"status": "ok", "items": [], "events": []}}


def build(existing, briefings, now, previous=None):
    return story_lifecycle.build_day(existing, previous, briefings, now, CONFIG)


def by_id(day):
    return {item["story_id"]: item for item in day["stories"]}


# --- a new story --------------------------------------------------------------------

def test_new_story_gets_first_seen_and_last_updated_and_the_new_badge():
    day = build(None, {"daily": briefing(story())}, NOW)

    item = day["stories"][0]
    assert day["date"] == "2026-10-16" and day["timezone"] == "Europe/Istanbul"
    assert item["first_seen_at"] == item["last_updated_at"] == "2026-10-16T09:00:00+00:00"
    assert item["badges"] == ["new"]
    assert item["story_id"] == item["id"] == story_lifecycle.stable_story_id("https://example.com/thy-cfm")


def test_story_id_is_a_stable_hash_of_the_canonical_source_url():
    first = story_lifecycle.stable_story_id("https://Example.com/a/?utm_source=x#frag")
    assert first == story_lifecycle.stable_story_id("https://example.com/a")
    assert first != story_lifecycle.stable_story_id("https://example.com/b")
    assert first.startswith("story-") and len(first) == len("story-") + 12


# --- a story that comes back ------------------------------------------------------------

def test_re_seen_story_keeps_first_seen_and_is_left_untouched():
    first = build(None, {"daily": briefing(story())}, NOW)
    again = story(headline="THY signs engine deal (reworded by the model)")
    again["detailed_analysis"] = ["a different analysis"]

    second = build(first, {"daily": briefing(again)}, NOW + 2 * HOUR)

    item = second["stories"][0]
    assert item["first_seen_at"] == first["stories"][0]["first_seen_at"]
    assert item["last_updated_at"] == first["stories"][0]["last_updated_at"]
    assert item["headline"] == "THY signs engine deal" and item["detailed_analysis"] == ["first analysis"]
    assert story_lifecycle.fingerprint(second) == story_lifecycle.fingerprint(first)   # nothing to commit


def test_same_story_from_both_modes_in_one_run_is_a_single_story():
    day = build(None, {"daily": briefing(story()), "hourly": briefing(story(), mode="hourly")}, NOW)
    assert len(day["stories"]) == 1


def test_a_reworded_story_from_another_source_is_matched_by_title_similarity():
    first = build(None, {"daily": briefing(story())}, NOW)
    other = story(url="https://other.example/engines", headline="Turkish signs engine deal", publishers=("Wire B",),
                  title="THY signs engine deal today")
    second = build(first, {"daily": briefing(other)}, NOW + HOUR)
    assert len(second["stories"]) == 1
    assert second["stories"][0]["source_count"] == 2          # and that new publisher counts as an update


def test_unrelated_stories_are_not_merged():
    first = build(None, {"daily": briefing(story())}, NOW)
    other = story(url="https://example.com/other", headline="Ryanair opens Poland base", title="Ryanair opens Poland base")
    assert len(build(first, {"daily": briefing(other)}, NOW + HOUR)["stories"]) == 2


# --- duplicates archived before they could be clustered -------------------------------------------------------------

DISTINCT_HEADLINES = ["Alpha engines agreement signed", "Bravo lounge reopens Frankfurt", "Charlie pilots ballot result", "Delta cargo terminal expansion"]


def cluster_story(urls, score=78.0, headline="THY and CFM sign MOU for 600 engines"):
    item = story(url=urls[0], headline=headline, score=score, publishers=("Wire A",))
    item["sources"] = [{"name": f"Wire {index}", "url": url, "title": f"title {index}"} for index, url in enumerate(urls)]
    item["source_count"] = len(urls)
    return item


def test_stored_duplicates_are_folded_into_the_oldest_story_without_losing_a_source():
    urls = [f"https://outlet{index}.example/thy-cfm" for index in range(4)]
    day = None
    for index, url in enumerate(urls):                      # four outlets archived at different hours as four stories
        day = build(day, {"daily": briefing(story(url=url, headline=DISTINCT_HEADLINES[index], title=DISTINCT_HEADLINES[index]))}, NOW + index * HOUR)
    assert len(day["stories"]) == 4
    oldest = min(day["stories"], key=lambda item: item["first_seen_at"])

    merged = build(day, {"daily": briefing(cluster_story(urls))}, NOW + 5 * HOUR)

    assert len(merged["stories"]) == 1
    item = merged["stories"][0]
    assert item["story_id"] == oldest["story_id"] and item["first_seen_at"] == oldest["first_seen_at"]
    assert {entry["url"] for entry in item["sources"]} >= set(urls)


def test_folding_duplicates_is_stable_on_the_next_run():
    urls = [f"https://outlet{index}.example/thy-cfm" for index in range(3)]
    day = None
    for index, url in enumerate(urls):
        day = build(day, {"daily": briefing(story(url=url, headline=DISTINCT_HEADLINES[index], title=DISTINCT_HEADLINES[index]))}, NOW + index * HOUR)
    merged = build(day, {"daily": briefing(cluster_story(urls))}, NOW + 4 * HOUR)
    again = build(merged, {"daily": briefing(cluster_story(urls))}, NOW + 5 * HOUR)
    assert story_lifecycle.fingerprint(again) == story_lifecycle.fingerprint(merged)


def test_unrelated_stored_stories_are_not_folded():
    first = build(None, {"daily": briefing(story(), story(url="https://example.com/b", headline="Airbus A220 order", title="Airbus A220 order"))}, NOW)
    second = build(first, {"daily": briefing(story(url="https://example.com/c", headline="Qantas network update", title="Qantas network update"))}, NOW + HOUR)
    assert len(second["stories"]) == 3


# --- a story whose score changed -----------------------------------------------------------

def test_score_change_at_the_threshold_marks_the_story_updated():
    minimum = CONFIG["updated"]["min_score_change"]
    first = build(None, {"daily": briefing(story(score=40.0))}, NOW)

    later = NOW + 2 * HOUR
    second = build(first, {"daily": briefing(story(score=40.0 + minimum, headline="THY engine deal, new details"))}, later)

    item = second["stories"][0]
    assert item["first_seen_at"] == first["stories"][0]["first_seen_at"]
    assert item["last_updated_at"] == story_lifecycle.to_iso(later)
    assert item["relevance_score"] == 40.0 + minimum and item["previous_score"] == 40.0
    assert item["update_reasons"] == ["score_change"]
    assert item["headline"] == "THY signs engine deal"                  # the narrative is kept ...
    assert item["narrative_status"] == "pending"                         # ... until a new one replaces it
    assert "updated" in story_lifecycle.compute_badges(item, later, CONFIG)


def test_score_change_below_the_threshold_is_not_an_update():
    minimum = CONFIG["updated"]["min_score_change"]
    first = build(None, {"daily": briefing(story(score=40.0))}, NOW)
    second = build(first, {"daily": briefing(story(score=40.0 + minimum - 0.1))}, NOW + HOUR)
    assert second["stories"][0]["last_updated_at"] == first["stories"][0]["last_updated_at"]
    assert second["stories"][0]["relevance_score"] == 40.0


def test_a_new_source_marks_the_story_updated_even_without_a_score_change():
    first = build(None, {"daily": briefing(story(publishers=("Wire A",)))}, NOW)
    later = NOW + HOUR
    second = build(first, {"daily": briefing(story(publishers=("Wire A", "Wire B")))}, later)
    item = second["stories"][0]
    assert item["update_reasons"] == ["new_source"] and item["source_count"] == 2
    assert [entry["name"] for entry in item["sources"]] == ["Wire A", "Wire B"]
    assert item["last_updated_at"] == story_lifecycle.to_iso(later)


# --- nothing is deleted --------------------------------------------------------------------

def test_stories_missing_from_a_later_run_stay_in_the_archive():
    first = build(None, {"daily": briefing(story(), story(url="https://example.com/b", headline="Airbus A220 order", title="Airbus A220 order"))}, NOW)
    second = build(first, {"daily": briefing(story(url="https://example.com/c", headline="Qantas network update", title="Qantas network update"))}, NOW + HOUR)
    assert {item["headline"] for item in second["stories"]} == {"THY signs engine deal", "Airbus A220 order", "Qantas network update"}


def test_the_previous_archive_object_is_never_mutated():
    first = build(None, {"daily": briefing(story())}, NOW)
    snapshot = copy.deepcopy(first)
    build(first, {"daily": briefing(story(score=90.0))}, NOW + HOUR)
    assert first == snapshot


# --- day rollover ----------------------------------------------------------------------------

def test_the_day_changes_at_istanbul_midnight_not_utc_midnight():
    before = datetime(2026, 10, 16, 20, 59, tzinfo=UTC)    # 23:59 in Istanbul
    after = datetime(2026, 10, 16, 21, 0, tzinfo=UTC)      # 00:00 on the 17th in Istanbul
    assert story_lifecycle.day_key(before, CONFIG) == "2026-10-16"
    assert story_lifecycle.day_key(after, CONFIG) == "2026-10-17"


def test_first_run_of_a_new_day_opens_a_new_file_and_leaves_yesterday_untouched():
    yesterday = build(None, {"daily": briefing(story())}, datetime(2026, 10, 16, 20, 0, tzinfo=UTC))
    frozen = copy.deepcopy(yesterday)
    new_morning = datetime(2026, 10, 16, 21, 30, tzinfo=UTC)   # 00:30 on the 17th in Istanbul
    fresh = story(url="https://example.com/b", headline="Airbus A220 order", title="Airbus A220 order", published=new_morning - HOUR)

    today = build(None, {"daily": briefing(fresh)}, new_morning, previous=yesterday)

    assert today["date"] == "2026-10-17"
    assert [item["headline"] for item in today["stories"]] == ["Airbus A220 order"]    # only what was seen today
    assert yesterday == frozen


def test_a_story_seen_yesterday_keeps_its_first_seen_when_it_returns_the_next_day():
    first_seen = datetime(2026, 10, 16, 20, 0, tzinfo=UTC)
    yesterday = build(None, {"daily": briefing(story(published=first_seen - HOUR))}, first_seen)
    next_day = datetime(2026, 10, 16, 21, 30, tzinfo=UTC)

    today = build(None, {"daily": briefing(story(published=first_seen - HOUR))}, next_day, previous=yesterday)

    item = today["stories"][0]
    assert item["first_seen_at"] == story_lifecycle.to_iso(first_seen)      # not reset to the new day
    assert item["badges"] == ["new"]                                         # still inside its 6 hours


def test_a_story_that_was_new_yesterday_is_not_new_again_after_the_window():
    first_seen = datetime(2026, 10, 16, 6, 0, tzinfo=UTC)
    yesterday = build(None, {"daily": briefing(story(published=first_seen - HOUR))}, first_seen)
    next_day = datetime(2026, 10, 16, 21, 30, tzinfo=UTC)
    today = build(None, {"daily": briefing(story(published=first_seen - HOUR))}, next_day, previous=yesterday)
    assert today["stories"][0]["badges"] == []


# --- badges expire on their own --------------------------------------------------------------

def stored(score=70.0, first_seen=NOW, last_updated=None, published=None, event_type="geopolitics_airspace"):
    return {"story_id": "s", "event_type": event_type, "first_seen_at": story_lifecycle.to_iso(first_seen),
            "last_updated_at": story_lifecycle.to_iso(last_updated or first_seen), "relevance_score": score,
            "published_at_iso": story_lifecycle.to_iso(published or first_seen - HOUR)}


@pytest.mark.parametrize("minutes, expected", [
    (0, ["breaking", "new"]),
    (179, ["breaking", "new"]),
    (181, ["new"]),            # breaking (3 h) is gone, new (6 h) stays
    (359, ["new"]),
    (361, []),                 # everything expired
])
def test_new_and_breaking_expire_after_their_configured_hours(minutes, expected):
    assert story_lifecycle.compute_badges(stored(), NOW + timedelta(minutes=minutes), CONFIG) == expected


def test_breaking_needs_a_score_above_the_critical_threshold():
    critical = CONFIG["breaking"]["critical_score"]
    assert "breaking" in story_lifecycle.compute_badges(stored(score=critical), NOW, CONFIG)
    assert "breaking" not in story_lifecycle.compute_badges(stored(score=critical - 0.1), NOW, CONFIG)


@pytest.mark.parametrize("minutes, expected", [(0, True), (359, True), (361, False)])
def test_updated_badge_expires_after_its_window(minutes, expected):
    item = stored(first_seen=NOW - 10 * HOUR, last_updated=NOW)
    assert ("updated" in story_lifecycle.compute_badges(item, NOW + timedelta(minutes=minutes), CONFIG)) is expected


def test_a_story_never_updated_does_not_get_the_updated_badge():
    assert "updated" not in story_lifecycle.compute_badges(stored(), NOW, CONFIG)


def test_old_news_seen_for_the_first_time_is_not_new_or_breaking():
    ancient = stored(published=NOW - timedelta(hours=CONFIG["max_publication_age_hours"] + 1))
    assert story_lifecycle.compute_badges(ancient, NOW, CONFIG) == []


def test_durations_and_thresholds_come_from_the_config():
    tight = {**CONFIG, "new": {"max_age_hours": 1}, "breaking": {**CONFIG["breaking"], "max_age_hours": 0.5, "critical_score": 95}}
    item = stored(score=70.0)
    assert story_lifecycle.compute_badges(item, NOW + timedelta(minutes=30), tight) == ["new"]
    assert story_lifecycle.compute_badges(item, NOW + timedelta(minutes=61), tight) == []


def test_ordering_puts_breaking_first_then_score_then_newest():
    day = {"stories": [
        {**stored(score=50.0), "story_id": "low-new", "first_seen_at": story_lifecycle.to_iso(NOW)},
        {**stored(score=80.0), "story_id": "breaking"},
        {**stored(score=55.0), "story_id": "mid"},
        {**stored(score=50.0, first_seen=NOW - 2 * HOUR), "story_id": "low-old"},
    ]}
    story_lifecycle.present_stories(day, NOW, CONFIG)
    assert [item["story_id"] for item in day["stories"]] == ["breaking", "mid", "low-new", "low-old"]


def test_present_stories_flags_overnight_stories():
    day = {
        "date": "2026-10-21",
        "stories": [
            {**stored(score=60.0), "story_id": "today", "published_at_iso": "2026-10-21T08:00:00+00:00"},
            {**stored(score=60.0), "story_id": "overnight", "published_at_iso": "2026-10-20T20:00:00+00:00"},
            {**stored(score=60.0), "story_id": "strategic", "published_at_iso": "2026-10-20T20:00:00+00:00", "strategic_publication": True},
        ],
    }
    story_lifecycle.present_stories(day, datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc), CONFIG)
    by_id = {s["story_id"]: s for s in day["stories"]}
    assert by_id["today"]["is_overnight"] is False
    assert by_id["overnight"]["is_overnight"] is True
    assert by_id["strategic"]["is_overnight"] is False


# --- relevance score -------------------------------------------------------------------------

def test_relevance_score_is_a_deterministic_weighted_sum_of_data():
    article = {"event_weight": 0.9, "reliability_weight": 1.0, "official": True,
               "entities": {"carriers": [{"tier": 1}], "groups": [], "airports": []}}
    v1 = story_lifecycle.load_relevance_config("v1")
    score, components = story_lifecycle.score_article(article, source_count=3, config=v1)
    assert components == {"event_type": 0.9, "source_reliability": 1.0, "entity_prominence": 1.0, "official_source": 1.0, "corroboration": 1.0}
    assert score == 100 * 0.9 * 0.35 + 20 + 25 + 10 + 10 == pytest.approx(96.5)
    assert story_lifecycle.score_article(article, source_count=3, config=v1) == (score, components)


def test_relevance_score_degrades_without_signals():
    score, components = story_lifecycle.score_article({}, source_count=1, config=story_lifecycle.load_relevance_config("v1"))
    assert components["entity_prominence"] == 0 and components["corroboration"] == 0 and components["official_source"] == 0
    assert score == pytest.approx(0.2 * 35 + 0.4 * 20)


def test_entity_prominence_uses_the_best_tier_of_any_matched_entity():
    entities = {"carriers": [{"tier": 3}], "groups": [{"tier": 2}], "airports": [{"tier": 4}]}
    assert story_lifecycle.best_tier(entities) == 2
    assert story_lifecycle.best_tier({"carriers": [], "groups": [], "airports": []}) is None


def test_enrich_adds_score_publishers_and_publication_time():
    articles = [
        {"title": "THY signs engine deal", "link": "https://a.example/thy", "source": "Wire A", "timestamp": NOW.timestamp(), "official": False},
        {"title": "THY signs engine deal today", "link": "https://b.example/thy", "source": "Wire B", "timestamp": NOW.timestamp() + 60},
        {"title": "Ryanair opens Poland base", "link": "https://c.example/fr", "source": "Wire C", "timestamp": NOW.timestamp()},
    ]
    stories = [{"headline": "THY deal", "original_source": {"url": "https://a.example/thy?utm_source=x", "title": "THY signs engine deal"}}]

    story_lifecycle.enrich_stories(stories, articles)

    item = stories[0]
    assert item["story_id"] == story_lifecycle.stable_story_id("https://a.example/thy")
    assert [entry["name"] for entry in item["sources"]] == ["Wire A", "Wire B"] and item["source_count"] == 2
    assert item["published_at_iso"] == story_lifecycle.to_iso(NOW)
    assert item["relevance_score"] > story_lifecycle.score_article(articles[0], 1)[0]   # corroboration adds to the score


# --- the API ------------------------------------------------------------------------------------

def install_store(monkeypatch, files, now=NOW):
    monkeypatch.setattr(briefing_store, "read_json", lambda path: copy.deepcopy(files.get(path)))
    monkeypatch.setattr(story_lifecycle, "utc_now", lambda: now)


def day_file(stories, date="2026-10-16", now=NOW):
    return build(None, {"daily": briefing(*stories)}, now) | {"date": date}


def test_api_returns_todays_file_with_badges_on_every_story(monkeypatch):
    day = day_file([story(score=80.0)])
    install_store(monkeypatch, {briefing_store.latest_path(): day, briefing_store.status_path(): {"status": "ok"}})

    result = _engine.get_ready_briefing("daily")

    assert result["status"] == "ok" and result["date"] == "2026-10-16"
    assert all("badges" in item for item in result["stories"])
    assert result["stories"][0]["badges"] == ["breaking", "new"]


def test_badges_in_the_api_expire_even_when_the_stored_file_is_older(monkeypatch):
    day = day_file([story(score=80.0)])
    assert day["stories"][0]["badges"] == ["breaking", "new"]                  # as written at 09:00
    later = NOW + 7 * HOUR
    install_store(monkeypatch, {briefing_store.latest_path(): day}, now=later)
    assert _engine.get_ready_briefing("daily")["stories"][0]["badges"] == []     # recomputed at read time


def test_api_serves_the_requested_day(monkeypatch):
    yesterday = day_file([story(headline="Yesterday's deal", url="https://example.com/y")], date="2026-10-15", now=NOW - 24 * HOUR)
    install_store(monkeypatch, {briefing_store.day_path("2026-10-15"): yesterday})

    result = _engine.get_ready_briefing("daily", date="2026-10-15")

    assert result["date"] == "2026-10-15" and result["stories"][0]["headline"] == "Yesterday's deal"
    assert result["status"] == "ok"      # an archived day is not stale just because it is old


def test_api_rejects_a_missing_or_malformed_date(monkeypatch):
    install_store(monkeypatch, {})
    with pytest.raises(_engine.BriefingNotFound):
        _engine.get_ready_briefing("daily", date="2026-01-01")
    for bad in ("2026-13-45", "yesterday", "2026-1-1", "../etc/passwd"):
        with pytest.raises(ValueError):
            _engine.get_ready_briefing("daily", date=bad)


def test_hourly_mode_shows_only_recent_stories_of_today(monkeypatch):
    old = story(headline="Morning story", url="https://example.com/old", published=NOW - 8 * HOUR)
    recent = story(headline="Fresh story", url="https://example.com/new", title="Fresh story")
    early = build(None, {"daily": briefing(old)}, NOW - 5 * HOUR)
    day = build(early, {"daily": briefing(recent)}, NOW)
    install_store(monkeypatch, {briefing_store.latest_path(): day})

    hourly = _engine.get_ready_briefing("hourly")
    daily = _engine.get_ready_briefing("daily")

    assert [item["headline"] for item in hourly["stories"]] == ["Fresh story"]
    assert {item["headline"] for item in daily["stories"]} == {"Fresh story", "Morning story"}


def test_latest_from_an_earlier_day_is_reported_stale(monkeypatch):
    old_day = day_file([story()], date="2026-10-15", now=NOW - 24 * HOUR)
    install_store(monkeypatch, {briefing_store.latest_path(): old_day})
    result = _engine.get_ready_briefing("daily")
    assert result["status"] == "stale" and "today" in result["warning"]


@pytest.fixture
def api_server():
    server = HTTPServer(("127.0.0.1", 0), briefing_handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def fetch(base, query):
    try:
        with urllib.request.urlopen(f"{base}/api/briefing?{query}", timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def test_http_endpoint_serves_today_by_default_and_a_day_by_date(api_server, monkeypatch):
    today = day_file([story()])
    past = day_file([story(url="https://example.com/p", headline="Past story")], date="2026-10-14", now=NOW - 48 * HOUR)
    files = {briefing_store.latest_path(): today, briefing_store.day_path("2026-10-14"): past}
    install_store(monkeypatch, files)
    # The Vercel handler imports its modules without the "api." prefix, so it holds separate copies.
    monkeypatch.setattr(sys.modules["briefing_store"], "read_json", lambda path: copy.deepcopy(files.get(path)))
    monkeypatch.setattr(sys.modules["story_lifecycle"], "utc_now", lambda: NOW)

    assert fetch(api_server, "mode=daily")[1]["date"] == "2026-10-16"
    status, body = fetch(api_server, "mode=daily&date=2026-10-14")
    assert status == 200 and body["stories"][0]["headline"] == "Past story" and "badges" in body["stories"][0]
    assert fetch(api_server, "date=2026-01-01")[0] == 404
    assert fetch(api_server, "date=not-a-date")[0] == 400


# --- the pipeline script ----------------------------------------------------------------------------

def collected(*stories, articles=100):
    return {"stories": [copy.deepcopy(item) for item in stories], "articles": articles, "candidates": len(stories),
            "market": {"status": "ok", "items": [], "events": []}}


def stub_collect(monkeypatch, outcome):
    def fake():
        if isinstance(outcome, Exception):
            raise outcome
        return copy.deepcopy(outcome)
    monkeypatch.setattr(_engine, "collect_run", fake)


def narrate_all(stories, api_key, description_limit, now=None):
    """A stand-in LLM step: every pending story gets a narrative."""
    pending = [item for item in stories if item.get("narrative_status") != "done"]
    for item in pending:
        item.update({"narrative_status": "done", "lead": "generated lead", "narrative_generated_at": "x"})
    return {"calls": 1 if pending else 0, "narrated": len(pending), "pending": 0, "error": ""}


def llm_down(stories, api_key, description_limit, now=None):
    pending = [item for item in stories if item.get("narrative_status") != "done"]
    return {"calls": 1 if pending else 0, "narrated": 0, "pending": len(pending), "error": "HTTP 429 after 4 attempts"}


def go(tmp_path, now, narrate=narrate_all):
    return run_pipeline.run(out_dir=tmp_path, now=now, api_key="test-key", narrate=narrate)


def read_out(out_dir, pathname):
    return json.loads((out_dir / pathname).read_text(encoding="utf-8"))


def candidate(**kwargs):
    item = story(**kwargs)
    item["narrative_status"] = "pending"
    return item


def test_first_run_writes_the_day_file_latest_and_status(tmp_path, monkeypatch):
    stub_collect(monkeypatch, collected(candidate()))

    assert go(tmp_path, NOW) == 0

    day = read_out(tmp_path, "briefings/2026-10-16.json")
    assert read_out(tmp_path, "briefings/latest.json") == day
    assert read_out(tmp_path, "briefings/status.json")["status"] == "ok"
    assert len(day["stories"]) == 1 and day["stories"][0]["narrative_status"] == "done"


def test_a_run_without_changes_commits_nothing(tmp_path, monkeypatch):
    stub_collect(monkeypatch, collected(candidate()))
    go(tmp_path, NOW)
    published = []
    monkeypatch.setattr(briefing_store, "publish", lambda files, message, repo_dir=None: published.append(files) or "ok")
    monkeypatch.setattr(briefing_store, "read_for_update", lambda pathname, repo_dir=None: read_out(tmp_path, pathname) if (tmp_path / pathname).exists() else None)

    assert run_pipeline.run(now=NOW + HOUR, api_key="k", narrate=narrate_all) == 0     # same story, same score, an hour later

    assert published == []


def test_a_new_story_is_published_to_the_day_file_and_latest_in_one_commit(tmp_path, monkeypatch):
    stub_collect(monkeypatch, collected(candidate()))
    go(tmp_path, NOW)
    published = []
    monkeypatch.setattr(briefing_store, "publish", lambda files, message, repo_dir=None: published.append(files) or "ok")
    monkeypatch.setattr(briefing_store, "read_for_update", lambda pathname, repo_dir=None: read_out(tmp_path, pathname) if (tmp_path / pathname).exists() else None)
    extra = candidate(url="https://example.com/b", headline="Airbus A220 order", title="Airbus A220 order")
    stub_collect(monkeypatch, collected(candidate(), extra))

    run_pipeline.run(now=NOW + HOUR, api_key="k", narrate=narrate_all)

    assert len(published) == 1
    assert sorted(published[0]) == ["briefings/2026-10-16.json", "briefings/latest.json"]
    assert published[0]["briefings/latest.json"] == published[0]["briefings/2026-10-16.json"]
    assert len(published[0]["briefings/2026-10-16.json"]["stories"]) == 2


def test_past_days_are_never_rewritten(tmp_path, monkeypatch):
    stub_collect(monkeypatch, collected(candidate()))
    go(tmp_path, NOW)
    before = (tmp_path / "briefings/2026-10-16.json").read_bytes()

    next_morning = datetime(2026, 10, 17, 6, 0, tzinfo=UTC)
    fresh = candidate(url="https://example.com/n", headline="Next day story", title="Next day story", published=next_morning - HOUR)
    stub_collect(monkeypatch, collected(fresh))
    go(tmp_path, next_morning)

    assert (tmp_path / "briefings/2026-10-16.json").read_bytes() == before
    assert read_out(tmp_path, "briefings/latest.json")["date"] == "2026-10-17"
    assert read_out(tmp_path, "briefings/2026-10-17.json")["stories"][0]["headline"] == "Next day story"


# --- the LLM failing is not a pipeline failure ---------------------------------------------------------

def test_llm_failure_still_publishes_scores_badges_and_the_archive(tmp_path, monkeypatch):
    stub_collect(monkeypatch, collected(candidate(score=75.0)))

    assert go(tmp_path, NOW, narrate=llm_down) == 0                  # the job does not go red

    day = read_out(tmp_path, "briefings/2026-10-16.json")
    item = day["stories"][0]
    assert item["narrative_status"] == "pending"
    assert item["relevance_score"] == 75.0 and item["first_seen_at"]
    assert "breaking" in story_lifecycle.compute_badges(item, NOW, CONFIG)
    status = read_out(tmp_path, "briefings/status.json")
    assert status["status"] == "ok" and status["narrative_pending"] == 1 and "429" in status["narrative_error"]


def test_pending_narratives_are_retried_on_the_next_run(tmp_path, monkeypatch):
    stub_collect(monkeypatch, collected(candidate()))
    go(tmp_path, NOW, narrate=llm_down)
    assert read_out(tmp_path, "briefings/2026-10-16.json")["stories"][0]["narrative_status"] == "pending"

    go(tmp_path, NOW + HOUR, narrate=narrate_all)                    # same story, the LLM is back

    item = read_out(tmp_path, "briefings/2026-10-16.json")["stories"][0]
    assert item["narrative_status"] == "done"
    assert item["first_seen_at"] == story_lifecycle.to_iso(NOW)       # nothing else about the story moved
    assert read_out(tmp_path, "briefings/status.json")["narrative_pending"] == 0


def test_a_story_with_a_finished_narrative_is_not_sent_to_the_llm_again(tmp_path, monkeypatch):
    stub_collect(monkeypatch, collected(candidate()))
    go(tmp_path, NOW)
    seen = []

    def spy(stories, api_key, description_limit, now=None):
        seen.append([item["story_id"] for item in stories if item.get("narrative_status") != "done"])
        return {"calls": 0, "narrated": 0, "pending": 0, "error": ""}

    go(tmp_path, NOW + HOUR, narrate=spy)
    assert seen == [[]]


# --- real failures --------------------------------------------------------------------------------------

def test_a_collection_failure_writes_stale_fails_the_run_and_leaves_the_archive_alone(tmp_path, monkeypatch):
    stub_collect(monkeypatch, collected(candidate()))
    go(tmp_path, NOW)
    archive = (tmp_path / "briefings/2026-10-16.json").read_bytes()

    stub_collect(monkeypatch, RuntimeError("No articles could be collected from any source"))
    assert go(tmp_path, NOW + HOUR) == 1

    assert (tmp_path / "briefings/2026-10-16.json").read_bytes() == archive
    status = read_out(tmp_path, "briefings/status.json")
    assert status["status"] == "stale" and "No articles" in status["errors"]["collect"]


def test_a_publish_failure_fails_the_run(monkeypatch):
    stub_collect(monkeypatch, collected(candidate()))
    monkeypatch.setattr(briefing_store, "read_for_update", lambda pathname, repo_dir=None: None)
    monkeypatch.setattr(briefing_store, "publish", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("push rejected")))
    assert run_pipeline.run(now=NOW, api_key="k", narrate=narrate_all) == 1


def test_status_alone_does_not_cause_a_commit_when_unchanged():
    report = {"calls": 1, "narrated": 0, "pending": 2, "error": "HTTP 429 after 4 attempts"}
    existing = run_pipeline.status_payload("", report, NOW)
    later_report = {"calls": 2, "narrated": 0, "pending": 2, "error": "HTTP 503 after 4 attempts"}
    assert not run_pipeline.status_changed(existing, run_pipeline.status_payload("", later_report, NOW + HOUR))
    assert run_pipeline.status_changed(existing, run_pipeline.status_payload("boom", report, NOW))
    assert run_pipeline.status_changed(existing, run_pipeline.status_payload("", {**report, "pending": 0}, NOW))
