import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from api import _engine, social_feed, source_catalog, source_probe
from scripts import collect_social, run_pipeline

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(hours=48)
SECRET = "private-session-value"


def post(post_id, text, hours_ago=2, airline="Delta Air Lines", code="DL", handle="Delta"):
    when = (NOW - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
    return {"id": post_id, "airline": airline, "airline_code": code, "platform": "X", "handle": handle, "text": text,
            "link": f"https://x.com/{handle}/status/{post_id}", "published_at": when}


def payload(*posts, generated_hours_ago=1):
    return {"generated_at": (NOW - timedelta(hours=generated_hours_ago)).isoformat(timespec="seconds"), "posts": list(posts)}


def collect(data):
    return social_feed.collect(NOW, CUTOFF, read_json=lambda path: data)


# --- reading what the local collector published -------------------------------------------------------------------------------------

def test_posts_become_official_headline_only_articles_with_the_posts_own_link():
    articles, report = collect(payload(post("1001", "We are adding 12 new routes from Atlanta this winter. Details: https://t.co/abc\nMore soon.")))
    article = articles[0]
    assert article["title"] == "We are adding 12 new routes from Atlanta this winter. Details:"
    assert article["link"] == "https://x.com/Delta/status/1001" and article["source"] == "Delta Air Lines on X"
    assert article["basis"] == "headline_only" and article["official"] is True and article["tier"] == 1 and article["airline_code"] == "DL"
    assert "t.co" not in article["description"] and len(article["description"]) <= 300
    assert report == {"status": "active", "error": "", "articles": 1, "posts_read": 1}


def test_old_posts_and_posts_without_a_link_or_time_are_dropped():
    bad = post("1002", "No time", 1)
    bad["published_at"] = ""
    data = payload(post("1003", "Too old", hours_ago=100), bad, dict(post("1004", "Not https"), link="http://x.com/a"), post("1005", "Kept"))
    articles, _ = collect(data)
    assert [article["title"] for article in articles] == ["Kept"]


def test_a_missing_or_empty_file_is_reported_not_silently_skipped():
    for data in (None, {}, payload()):
        articles, report = collect(data)
        assert articles == [] and report["status"] == "not_configured" and report["error"]


def test_a_file_older_than_36_hours_is_shown_as_a_visible_problem():
    _, report = collect(payload(post("1006", "Still readable"), generated_hours_ago=40))
    assert report["status"] == "active" and "36" in report["error"]
    health = run_pipeline.source_health({social_feed.SOURCE_NAME: report}, {}, NOW)
    assert health[social_feed.SOURCE_NAME]["status"] == run_pipeline.STATUS_FETCH_ERROR


def test_x_timestamps_are_understood():
    assert social_feed.parse_time("Mon Oct 19 08:30:00 +0000 2026") == datetime(2026, 10, 19, 8, 30, tzinfo=timezone.utc)
    assert social_feed.parse_time("2026-10-19T08:30:00Z") == datetime(2026, 10, 19, 8, 30, tzinfo=timezone.utc)


def test_a_long_first_line_is_cut_at_a_word_boundary():
    title = social_feed.post_title("word " * 60)
    assert len(title) <= social_feed.TITLE_CHARS + 1 and title.endswith("…")


# --- catalog, engine, probe ------------------------------------------------------------------------------------------------------------

def test_one_logical_source_with_the_commercial_risk_flag():
    rows = {row["name"]: row for row in source_catalog.read_rows()}
    row = rows[social_feed.SOURCE_NAME]
    assert row["source_type"] == "airline_ir" and row["official"] == "true" and row["mode"] == "feed_only" and row["commercial_use_risk"] == "high"
    assert row["status"] == "active" and row["active"] == "1"


def test_the_generic_reader_and_the_probe_leave_it_alone_and_the_engine_reads_it():
    row = {row["name"]: row for row in source_catalog.read_rows()}[social_feed.SOURCE_NAME]
    record, articles = source_probe.probe_source(row, social_feed.catalog_record(), {}, {}, NOW)
    assert articles == [] and record["requests"] == 0 and record["status"] == "active"
    engine = open(_engine.__file__, encoding="utf-8").read()
    assert "social_feed.collect(" in engine and "social_feed.SOURCE_NAME}" in engine


# --- the local collector --------------------------------------------------------------------------------------------------------------

def raw(post_id, text, created=None, **extra):
    created = created or (NOW - timedelta(hours=1)).strftime("%a %b %d %H:%M:%S +0000 %Y")
    return {"id": post_id, "text": text, "createdAt": created, **extra}


def runner_for(outputs, calls=None):
    def run(command, **kwargs):
        if calls is not None:
            calls.append((command, kwargs))
        output = outputs.get(command[-4], outputs.get("*"))
        return SimpleNamespace(returncode=0 if output is not None else 1, stdout=json.dumps(output), stderr=SECRET)
    return run


ACCOUNT = {"airline": "Delta Air Lines", "airline_code": "DL", "platform": "X", "handle": "Delta"}


def test_replies_reposts_and_old_posts_are_skipped_and_links_are_built():
    old = (NOW - timedelta(days=30)).strftime("%a %b %d %H:%M:%S +0000 %Y")
    outputs = {"*": [raw("11", "Original"), raw("12", "reply", inReplyToStatusId="5"), raw("13", "RT", isRetweet=True), raw("14", "Old", created=old), {"id": "x"}]}
    posts, note = collect_social.read_account(ACCOUNT, ("a", "b"), runner_for(outputs), NOW)
    assert [p["id"] for p in posts] == ["11"] and posts[0]["link"] == "https://x.com/Delta/status/11" and note == ""


def test_the_session_goes_only_into_the_environment_and_never_into_output_or_notes(capsys, monkeypatch):
    calls = []
    posts, note = collect_social.read_account(ACCOUNT, (SECRET, "csrf-value"), runner_for({"*": [raw("21", "Hello")]}, calls), NOW)
    command, kwargs = calls[0]
    assert SECRET not in json.dumps(command) and kwargs["env"]["AUTH_TOKEN"] == SECRET
    assert SECRET not in json.dumps(posts) and SECRET not in note
    failing = lambda *a, **k: (_ for _ in ()).throw(OSError(f"cannot run with {SECRET}"))
    _, failure_note = collect_social.read_account(ACCOUNT, (SECRET, "c"), failing, NOW)
    assert failure_note == "reader error: OSError"


def test_a_failing_account_keeps_its_earlier_posts_and_is_named_in_the_notes():
    earlier = [post("31", "Earlier post", hours_ago=30)]
    accounts = [ACCOUNT, dict(ACCOUNT, handle="United", airline="United Airlines", airline_code="UA")]
    outputs = {"Delta": [raw("32", "Fresh")], "United": None}
    data, notes = collect_social.collect(accounts, ("a", "b"), earlier, runner_for(outputs), sleep=lambda s: None, now=NOW)
    assert {p["id"] for p in data["posts"]} == {"31", "32"} and notes == {"United": "reader failed"}


def test_accounts_are_read_one_at_a_time_with_a_pause():
    pauses = []
    collect_social.collect([ACCOUNT, ACCOUNT, ACCOUNT], ("a", "b"), None, runner_for({"*": []}), sleep=pauses.append, now=NOW)
    assert pauses == [collect_social.GAP_SECONDS] * 2


def test_the_account_list_is_data_and_every_entry_is_complete():
    accounts = collect_social.load_accounts()
    assert len(accounts) >= 10 and len({a["handle"] for a in accounts}) == len(accounts)
    assert all(a["airline"] and a["airline_code"] and a["handle"] and a["platform"] == "X" for a in accounts)


def test_without_a_saved_session_the_collector_stops_with_a_message(monkeypatch, capsys):
    monkeypatch.setattr(collect_social, "saved_session", lambda: (None, None))
    monkeypatch.setattr(collect_social.connect_social, "BIRD_SCRIPT", collect_social.PROJECT_DIR / "api" / "social_feed.py")
    monkeypatch.setattr(collect_social.shutil, "which", lambda name: "node")
    assert collect_social.main([]) == 1 and "connect_social.cmd" in capsys.readouterr().out


def test_mainstream_news_wire_social_accounts_are_monitored_and_filtered_for_aviation():
    accounts = collect_social.load_accounts()
    handles = {a["handle"] for a in accounts}
    for wire in ("ReutersBiz", "business", "FT", "WSJ", "CNBC"):
        assert wire in handles

    # A mainstream post about airlines is kept and marked as flash alert with tier 2 and official=False
    aviation_post = post("2001", "Delta Air Lines reports record quarterly transatlantic demand: https://t.co/abc",
                         airline="Reuters", code="RTR", handle="ReutersBiz")
    articles, _ = collect(payload(aviation_post))
    assert len(articles) == 1
    assert articles[0]["is_flash_alert"] is True
    assert articles[0]["official"] is False
    assert articles[0]["tier"] == 2
    assert articles[0]["source_type"] == "social"
    assert "Delta" in articles[0]["title"]

    # A mainstream post unrelated to aviation (e.g. crypto/tech) is filtered out
    off_topic_post = post("2002", "Bitcoin reaches new milestone amid tech earnings rally: https://t.co/xyz",
                          airline="Reuters", code="RTR", handle="ReutersBiz")
    articles, _ = collect(payload(off_topic_post))
    assert len(articles) == 0

    # A routine official airline post is official tier 1, but NOT an urgent flash alert
    routine_airline_post = post("2003", "Welcome to our new Airbus A350 aircraft joining the fleet: https://t.co/plane",
                                airline="Turkish Airlines", code="TK", handle="TurkishAirlines")
    articles, _ = collect(payload(routine_airline_post))
    assert len(articles) == 1
    assert articles[0]["official"] is True
    assert articles[0]["tier"] == 1
    assert articles[0]["source_type"] == "official_social"
    assert articles[0]["is_flash_alert"] is False

