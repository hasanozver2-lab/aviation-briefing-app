import json
import urllib.error
from datetime import datetime, timezone

import pytest

from api import narrative, story_lifecycle

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
CONFIG = narrative.load_narrative_config()
RETRY = CONFIG["retry"]
DESCRIPTION_LIMIT = 800


def stories(count, status="pending", start=0):
    return [
        {"story_id": f"story-{index:03d}", "relevance_score": 90.0 - index, "narrative_status": status,
         "headline": f"uniqueword{index:03d} update", "original_source": {"title": f"uniqueword{index:03d} update", "source_name": "Wire"},
         "source_description": "x" * 1500, "source_count": 1, "first_seen_at": "2026-10-16T08:00:00+00:00"}
        for index in range(start, start + count)
    ]


def gemini_answer(items, skip=()):
    produced = [
        {"story_id": item["story_id"], "headline": f"Headline {item['story_id']}", "lead": "A lead.",
         "detailed_analysis": ["first", "second"], "data_points": ["600 engines"], "strategic_impact": "Impact.",
         "market_exposure": [{"carrier": "Carrier A", "impact": "Positive", "details": "d"}], "why_it_matters": "Because."}
        for item in items if item["story_id"] not in skip
    ]
    return {"candidates": [{"content": {"parts": [{"text": json.dumps({"stories": produced})}]}}]}


class FakeLlm:
    """Records every request; `failures` are raised first, one per attempt, then it answers."""

    def __init__(self, failures=(), answer=gemini_answer):
        self.requests, self.failures, self.answer = [], list(failures), answer

    def post(self, items):
        self.requests.append(items)
        if self.failures:
            raise self.failures.pop(0)
        return self.answer(items)


def http_error(code, retry_after=None):
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    return urllib.error.HTTPError("https://example.invalid/v1", code, "error", headers, None)


def fill(items, llm, api_key="test-key"):
    sleeps = []
    report = narrative.fill_pending(items, api_key, DESCRIPTION_LIMIT, config=CONFIG, post=llm.post, sleep=sleeps.append, now=NOW)
    return report, sleeps


# --- one batched call, stored per story_id ---------------------------------------------------------

def test_pending_stories_share_one_batched_call_and_are_stored_on_the_story():
    items, llm = stories(5), FakeLlm()

    report, _ = fill(items, llm)

    assert report == {"calls": 1, "narrated": 5, "pending": 0, "error": ""}
    assert len(llm.requests) == 1 and len(llm.requests[0]) == 5
    assert all(item["narrative_status"] == "done" and item["lead"] == "A lead." for item in items)
    assert items[0]["narrative_generated_at"] == "2026-10-16T09:00:00+00:00"
    assert items[0]["headline"] == "Headline story-000"


def test_a_story_whose_narrative_is_done_costs_no_call():
    items, llm = stories(3, status="done"), FakeLlm()
    report, _ = fill(items, llm)
    assert report["calls"] == 0 and llm.requests == []


def test_more_than_one_batch_uses_a_second_call_and_the_run_is_capped():
    batch, calls = CONFIG["max_stories_per_call"], CONFIG["max_calls_per_run"]
    items, llm = stories(batch * calls + 1), FakeLlm()

    report, _ = fill(items, llm)

    assert report["calls"] == calls and len(llm.requests) == calls
    assert report["narrated"] == batch * calls and report["pending"] == 1
    assert items[-1]["narrative_status"] == "pending"                 # the lowest-scoring story waits for the next run


def test_highest_scoring_stories_are_narrated_first():
    items = stories(CONFIG["max_stories_per_call"] * CONFIG["max_calls_per_run"] + 3)
    llm = FakeLlm()
    fill(items, llm)
    assert [item["narrative_status"] for item in items[:-3]] == ["done"] * (len(items) - 3)
    assert [item["narrative_status"] for item in items[-3:]] == ["pending"] * 3


def test_the_request_carries_story_text_but_no_secret_and_respects_the_description_limit():
    llm = FakeLlm()
    fill(stories(1), llm, api_key="SECRET-KEY-VALUE")
    sent = json.dumps(llm.requests[0])
    assert "SECRET-KEY-VALUE" not in sent
    assert len(llm.requests[0][0]["description"]) == DESCRIPTION_LIMIT


def test_narrative_leaves_score_badges_and_first_seen_untouched():
    item = stories(1)[0]
    item["badges"] = ["new"]
    before = {key: item[key] for key in ("relevance_score", "badges", "first_seen_at", "story_id")}
    fill([item], FakeLlm())
    assert {key: item[key] for key in before} == before


# --- backoff and retries ----------------------------------------------------------------------------

@pytest.mark.parametrize("attempt, delay", [(1, 2), (2, 4), (3, 8), (4, 16), (5, 30), (9, 30)])
def test_backoff_is_exponential_and_capped(attempt, delay):
    assert narrative.retry_delay(attempt, RETRY) == delay


def test_a_server_retry_after_is_honoured_but_capped():
    assert narrative.retry_delay(1, RETRY, retry_after=5) == 5
    assert narrative.retry_delay(1, RETRY, retry_after=1) == 2
    assert narrative.retry_delay(1, RETRY, retry_after=3600) == RETRY["max_delay_seconds"]


def test_429_is_retried_with_exponential_backoff_until_it_succeeds():
    items, llm = stories(2), FakeLlm(failures=[http_error(429), http_error(429), http_error(503)])

    report, sleeps = fill(items, llm)

    assert len(llm.requests) == 4 and sleeps == [2, 4, 8]
    assert report["narrated"] == 2 and report["error"] == ""


def test_persistent_429_gives_up_after_the_limited_number_of_attempts_without_raising():
    items = stories(2)
    llm = FakeLlm(failures=[http_error(429)] * 10)

    report, sleeps = fill(items, llm)

    assert len(llm.requests) == RETRY["max_attempts"] == 4
    assert sleeps == [2, 4, 8]
    assert report["error"] == "HTTP 429 after 4 attempts" and report["narrated"] == 0 and report["pending"] == 2
    assert all(item["narrative_status"] == "pending" for item in items)


def test_after_a_failed_batch_the_run_stops_instead_of_hammering_the_api():
    items = stories(CONFIG["max_stories_per_call"] + 1)
    llm = FakeLlm(failures=[http_error(429)] * 10)
    fill(items, llm)
    assert len(llm.requests) == RETRY["max_attempts"]                 # the second batch was never tried


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_client_errors_are_not_retried(code):
    llm = FakeLlm(failures=[http_error(code)])
    report, sleeps = fill(stories(1), llm)
    assert len(llm.requests) == 1 and sleeps == []
    assert report["error"] == f"HTTP {code} (not retried)"


def test_network_errors_are_retried():
    llm = FakeLlm(failures=[urllib.error.URLError("reset"), TimeoutError()])
    report, sleeps = fill(stories(1), llm)
    assert report["narrated"] == 1 and sleeps == [2, 4]


def test_a_retry_after_header_sets_the_wait():
    llm = FakeLlm(failures=[http_error(429, retry_after=7)])
    _, sleeps = fill(stories(1), llm)
    assert sleeps == [7]


def test_without_an_api_key_nothing_is_called_and_stories_stay_pending():
    items, llm = stories(2), FakeLlm()
    report, _ = fill(items, llm, api_key="")
    assert llm.requests == [] and report["pending"] == 2 and "GEMINI_API_KEY" in report["error"]


# --- bad answers ---------------------------------------------------------------------------------------

def test_an_unreadable_answer_leaves_stories_pending():
    llm = FakeLlm(answer=lambda items: {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]})
    items = stories(2)
    report, _ = fill(items, llm)
    assert report["narrated"] == 0 and "unreadable" in report["error"]
    assert all(item["narrative_status"] == "pending" for item in items)


def test_unknown_ids_and_incomplete_items_are_ignored():
    def answer(items):
        good = gemini_answer(items, skip={items[1]["story_id"], items[2]["story_id"]})
        data = json.loads(good["candidates"][0]["content"]["parts"][0]["text"])
        data["stories"].append({"story_id": "story-not-requested", "headline": "x", "lead": "y"})
        data["stories"].append({"story_id": items[2]["story_id"], "headline": "", "lead": ""})
        good["candidates"][0]["content"]["parts"][0]["text"] = json.dumps(data)
        return good

    items = stories(3)
    report, _ = fill(items, FakeLlm(answer=answer))
    assert [item["narrative_status"] for item in items] == ["done", "pending", "pending"]
    assert report["narrated"] == 1 and report["pending"] == 2


# --- a changed story is regenerated, an unchanged one is not ------------------------------------------------

def day_with_done_story():
    config = story_lifecycle.load_badges_config()
    item = {**stories(1, status="done")[0], "story_id": "story-aaa", "relevance_score": 40.0, "id": "story-aaa",
            "original_source": {"url": "https://example.com/a", "title": "T", "source_name": "Wire A"},
            "sources": [{"name": "Wire A", "url": "https://example.com/a", "title": "T"}], "source_count": 1,
            "first_seen_at": "2026-10-16T08:00:00+00:00", "last_updated_at": "2026-10-16T08:00:00+00:00",
            "lead": "old lead", "headline": "Old headline"}
    return config, {"date": "2026-10-16", "stories": [item]}


def incoming(item, **changes):
    fresh = {**item, "narrative_status": "pending", "lead": "", "headline": "raw source title", **changes}
    return {"daily": {"status": "ok", "stories": [fresh]}}


def test_an_unchanged_story_keeps_its_narrative_and_costs_no_call():
    config, day = day_with_done_story()
    merged = story_lifecycle.build_day(day, None, incoming(day["stories"][0]), NOW, config)
    llm = FakeLlm()
    report, _ = fill(merged["stories"], llm)
    assert report["calls"] == 0 and merged["stories"][0]["lead"] == "old lead"


def test_a_materially_updated_story_keeps_its_old_text_until_a_new_one_is_generated():
    config, day = day_with_done_story()
    changed = incoming(day["stories"][0], relevance_score=60.0)
    merged = story_lifecycle.build_day(day, None, changed, NOW, config)
    item = merged["stories"][0]
    assert item["narrative_status"] == "pending" and item["lead"] == "old lead" and item["headline"] == "Old headline"

    llm = FakeLlm()
    report, _ = fill(merged["stories"], llm)

    assert report["calls"] == 1 and item["lead"] == "A lead." and item["narrative_status"] == "done"


def test_call_counts_over_three_hourly_runs():
    """New stories cost one batched call, an unchanged hour costs none, two more stories cost one."""
    config = story_lifecycle.load_badges_config()
    llm = FakeLlm()
    day, calls = None, []

    def hour(candidates, offset):
        nonlocal day
        stories_in = [{**s, "story_id": s["story_id"], "id": s["story_id"], "sources": [], "source_count": 1,
                       "original_source": {"url": f"https://example.com/{s['story_id']}", "title": s["headline"], "source_name": "Wire"}}
                      for s in candidates]
        day = story_lifecycle.build_day(day, None, {"daily": {"status": "ok", "stories": stories_in}}, NOW.replace(hour=9 + offset), config)
        report, _ = fill(day["stories"], llm)
        calls.append(report["calls"])

    base = stories(6)
    hour(base, 0)
    hour(base, 1)
    hour(base + stories(2, start=6), 2)

    assert calls == [1, 0, 1]
