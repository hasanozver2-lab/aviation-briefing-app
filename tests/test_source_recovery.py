import copy
from datetime import datetime, timezone

import pytest

from api import _engine, source_catalog, source_recovery
from scripts import run_pipeline


NOW = datetime(2026, 10, 19, 5, tzinfo=timezone.utc)
TITLE = "Turkish Airlines orders 600 CFM engines"


def legacy(title=TITLE, publisher="Aviation Week"):
    return {"story_id": "stable-id", "headline": "Unsupported generated headline",
            "first_seen_at": "2026-10-18T10:00:00+00:00", "published_at_iso": NOW.isoformat(),
            "lead": "Unsupported analysis", "narrative_status": "done", "relevance_score": 60,
            "original_source": {"title": title, "source_name": publisher,
                                "url": "https://news.google.com/rss/articles/old"}, "sources": []}


def direct(title=TITLE):
    return {"story_id": "new-id", "headline": title, "published_at_iso": NOW.isoformat(),
            "relevance_score": 60, "source_description": "Publisher summary",
            "original_source": {"title": title, "source_name": "Delta News Hub",
                                "url": "https://news.delta.com/release"},
            "sources": [{"name": "Delta News Hub", "title": title, "url": "https://news.delta.com/release"}]}


def test_recovery_retains_history_and_uses_only_direct_evidence():
    archive = {"stories": [legacy()]}
    original = copy.deepcopy(archive)
    recovered, count = source_recovery.reconcile_day(archive, [direct()], NOW)
    story = recovered["stories"][0]
    assert count == 1 and archive == original
    assert story["story_id"] == "stable-id"
    assert story["first_seen_at"] == original["stories"][0]["first_seen_at"]
    assert story["headline"] == TITLE and "lead" not in story
    assert story["narrative_status"] == "pending"
    assert story["source_verification_status"] == "verified"
    assert story["published_at_iso"] == direct()["published_at_iso"]
    assert source_recovery.reconcile_day(recovered, [direct()], NOW)[1] == 0


@pytest.mark.parametrize("override", [{"active": "0"}, {"status": "excluded_policy"},
                                    {"license_status": "paid"}, {"notes": '{"license_required": true}'}])
def test_disabled_or_restricted_publishers_cannot_confirm_a_story(monkeypatch, override):
    row = {"name": "Delta", "url": "https://news.delta.com", "active": "1",
           "status": "active", "license_status": "public", "notes": "{}", **override}
    monkeypatch.setattr(source_catalog, "read_rows", lambda: [row])
    assert source_recovery.reconcile_day({"stories": [legacy()]}, [direct()], NOW)[1] == 0


@pytest.mark.parametrize("candidate", [
    direct("Turkish Airlines orders 300 CFM engines"),
    direct("Lufthansa resumes Tokyo flights"),
    {**direct(), "published_at_iso": "2026-09-01T00:00:00+00:00"},
    {**direct(), "published_at_iso": ""},
])
def test_conflicting_numbers_unrelated_titles_and_dates_do_not_confirm(candidate):
    assert source_recovery.reconcile_day({"stories": [legacy()]}, [candidate], NOW)[1] == 0


def test_pending_titles_never_expose_generated_analysis_search_links_scores_or_badges():
    result = source_recovery.pending_titles({"stories": [legacy()]}, "2026-10-19")
    assert len(result) == 1 and result[0]["headline"] == TITLE
    assert set(result[0]) == {"story_id", "headline", "reported_source", "language", "source_verification_status"}
    assert source_recovery.pending_titles({"stories": [legacy()]}, "2026-10-20") == []


@pytest.mark.parametrize("publisher", ["Reuters", "Bloomberg", "Financial Times", "Associated Press"])
def test_policy_exclusions_apply_to_waiting_area(publisher):
    assert source_recovery.pending_titles({"stories": [legacy(publisher=publisher)]}) == []


@pytest.mark.parametrize("title", ["Why I'd Buy Airline Stock Today", "Armored attack helicopter delivery"])
def test_commentary_and_military_do_not_enter_waiting_area(title):
    assert source_recovery.pending_titles({"stories": [legacy(title=title)]}) == []


def test_api_separates_waiting_titles_from_verified_stories_without_rewriting_archive(monkeypatch):
    archive = {"date": "2026-10-19", "stories": [legacy()], "status": "ok"}
    saved = copy.deepcopy(archive)
    monkeypatch.setattr(_engine.story_lifecycle, "utc_now", lambda: NOW)
    monkeypatch.setattr(_engine.briefing_store, "read_json", lambda path: copy.deepcopy(archive) if "status" not in path else {})
    result = _engine.get_ready_briefing()
    assert result["stories"] == [] and result["verification_pending_count"] == 1
    assert result["verification_pending_stories"][0]["headline"] == TITLE
    assert result["excluded_count"] == 1 and archive == saved


def test_pipeline_repairs_from_all_candidates_even_when_not_selected_for_this_run():
    archive = {"date": "2026-10-19", "stories": [legacy()], "status": "ok"}
    seen = []

    def narrate(stories, *args, **kwargs):
        seen.extend(stories)
        return {"calls": 0, "narrated": 0, "pending": len(stories), "error": ""}

    def read(path):
        return copy.deepcopy(archive) if path.endswith("2026-10-19.json") else None

    collected = {"stories": [], "market": {}, "verification_candidates": [direct()]}
    files, report = run_pipeline.plan_files(collected, "", read, NOW, "", narrate=narrate)
    recovered = files["briefings/2026-10-19.json"]["stories"][0]
    assert recovered["story_id"] == "stable-id" and recovered["narrative_status"] == "pending"
    assert recovered["first_seen_at"] == archive["stories"][0]["first_seen_at"]
    assert [story["story_id"] for story in seen] == ["stable-id"]


def test_unverified_archive_stories_never_reach_the_narrator():
    archive = {"date": "2026-10-19", "stories": [legacy()], "status": "ok"}
    seen = []

    def narrate(stories, *args, **kwargs):
        seen.extend(stories)
        return {"calls": 0, "narrated": 0, "pending": len(stories), "error": ""}

    run_pipeline.plan_files({"stories": [], "market": {}}, "",
                            lambda path: copy.deepcopy(archive) if path.endswith("2026-10-19.json") else None,
                            NOW, "", narrate=narrate)
    assert seen == []
