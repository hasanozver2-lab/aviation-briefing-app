import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from api import _engine, briefing_store, entities, feed_discovery as fd, feed_sources, narrative, source_catalog, story_lifecycle

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
REAL_FETCHER = fd.PoliteFetcher
RECENT = (NOW - timedelta(hours=3)).strftime("%a, %d %b %Y %H:%M:%S +0000")


def rss(items):
    body = "".join(f"<item><title>{t}</title><link>{l}</link><pubDate>{d}</pubDate><description>{s}</description></item>" for t, l, d, s in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'.encode()


class Site:
    def __init__(self, pages):
        self.pages, self.log = pages, []

    def __call__(self, url, headers, timeout):
        self.log.append(url)
        status, body = self.pages.get(url, (404, b""))
        return fd.Response(status, body, {}, url, 0.01, "" if status == 200 else f"HTTPError {status}")


def row(name="Wire Example", **overrides):
    base = {"name": name, "url": "https://wire.example/", "feed_url": "", "feed_type": "rss", "region": "Global", "tier": "3", "license_status": "public", "language": "en",
            "active": "1", "notes": json.dumps({"discovery_urls": ["https://wire.example/"], "category_hint": "Other areas"}), "source_type": "wire_headline",
            "official": "false", "mode": "feed_only", "timeout_s": "10", "status": "active", "reason": "", "commercial_use_risk": "high"}
    base.update(overrides)
    return base


def source(**overrides):
    return feed_sources.source_record(row(**overrides))


def fetcher_for(site):
    return fd.PoliteFetcher(fetch=site, sleep=lambda s: None)


FEED = rss([("Airline X orders 50 jets from Airbus", "https://wire.example/a1", RECENT, "The carrier confirmed the order on Friday. Details were not disclosed."),
            ("Central bank holds interest rates", "https://wire.example/a2", RECENT, "Rates unchanged.")])
DISCOVERED = {"wire_example": {"feed_url": "https://wire.example/feed", "method": "rss", "verified_at": "2026-10-16T00:00:00+00:00", "last_ok_at": "2026-10-16T00:00:00+00:00", "item_count_90d": 2}}


# --- the catalog source record ----------------------------------------------------------------------------------------

def test_the_source_record_carries_type_mode_tier_weight_and_filter_rule():
    record = source()
    assert (record["mode"], record["source_type"], record["tier"], record["reliability_weight"], record["aviation_filter"]) == ("feed_only", "wire_headline", 3, 0.7, True)
    assert source(source_type="airline_ir", official="true", tier="1", mode="full")["aviation_filter"] is False
    overridden = source(source_type="oem", notes=json.dumps({"aviation_filter": True}))
    assert overridden["aviation_filter"] is True


def test_only_active_catalog_rows_not_already_read_by_the_legacy_loop_are_used():
    rows = [row("Active One"), row("Blocked One", status="disabled_blocked", active="0"), row("Legacy One")]
    chosen = feed_sources.catalog_feed_sources(rows, handled_names={"Legacy One"})
    assert [item["name"] for item in chosen] == ["Active One"]


def test_sources_are_grouped_by_host_so_one_host_is_never_read_twice_at_once():
    a, b = source(), source()
    b["name"], b["discovery_urls"] = "Other Wire", ["https://other.example/"]
    c = source()
    c["name"], c["discovery_urls"] = "Wire Sports", ["https://news.wire.example/sports"]
    groups = feed_sources.group_by_host([a, b, c])
    assert sorted(len(v) for v in groups.values()) == [1, 2]
    assert [s["name"] for s in groups["wire.example"]] == ["Wire Example", "Wire Sports"]


# --- the aviation filter --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("title, summary, expected", [
    ("Airline X orders 50 jets from Airbus", "", True),
    ("Central bank holds interest rates", "Rates unchanged.", False),
    ("Quarterly revenue beats forecast", "profit and security spending rose", False),      # the broad business words are not enough
    ("Strike at the airport delays flights", "", True),
    ("Boeing deliveries slip", "", True),
    ("Cairport shopping festival", "", False),                                            # whole words only
])
def test_the_strict_aviation_filter(title, summary, expected):
    assert feed_sources.passes_aviation_filter({"title": title, "description": summary}) is expected


def test_a_matched_carrier_entity_passes_without_a_keyword():
    article = {"title": "Lufthansa and unions meet Tuesday", "description": "", "entities": {"carriers": [{"entity_id": "carrier:1"}]}}
    assert feed_sources.passes_aviation_filter(article)


def test_filter_for_aviation_annotates_with_entities_and_drops_the_rest():
    index = entities.EntityIndex.from_csv()
    articles = [{"title": "Lufthansa adds Tokyo flights", "description": ""}, {"title": "Oil futures rise on supply worries", "description": ""}]
    kept, dropped = feed_sources.filter_for_aviation(articles, index)
    assert [a["title"] for a in kept] == ["Lufthansa adds Tokyo flights"] and dropped == 1


def test_edgar_items_are_selected_by_number():
    assert feed_sources.edgar_items_wanted("Filed: 2026-10-16 Item 2.02: Results Item 9.01: Exhibits", ["2.02", "7.01", "8.01"])
    assert not feed_sources.edgar_items_wanted("Item 5.02: Departure of Directors Item 9.01", ["2.02", "7.01", "8.01"])
    assert not feed_sources.edgar_items_wanted("", ["2.02"])


# --- reading a source ---------------------------------------------------------------------------------------------------

def test_a_stored_feed_is_read_without_touching_any_article_page():
    site = Site({"https://wire.example/feed": (200, FEED)})
    articles, report = feed_sources.read_source(source(), DISCOVERED, fetcher_for(site), NOW, NOW - timedelta(hours=48))
    assert [a["link"] for a in articles] == ["https://wire.example/a1", "https://wire.example/a2"]
    assert site.log == ["https://wire.example/feed"]
    assert not any(url.endswith(("/a1", "/a2")) for url in site.log), "article pages must never be requested"
    assert report["status"] == "active" and report["method"] == "rss" and report["articles"] == 2


def test_feed_only_articles_hold_nothing_but_feed_fields_and_a_short_summary():
    long_summary = "word " * 400
    feed = rss([("Carrier opens base in Lisbon", "https://wire.example/a1", RECENT, long_summary)])
    articles, _ = feed_sources.read_source(source(), DISCOVERED, fetcher_for(Site({"https://wire.example/feed": (200, feed)})), NOW, NOW - timedelta(hours=48))
    article = articles[0]
    assert article["basis"] == "headline_only" and len(article["description"]) <= feed_sources.FEED_ONLY_SUMMARY_CHARS
    assert article["source_type"] == "wire_headline" and article["reliability_weight"] == 0.7 and article["official"] is False


def test_a_full_mode_source_keeps_its_summary_and_has_no_basis_marker():
    feed = rss([("Carrier opens base in Lisbon", "https://wire.example/a1", RECENT, "x" * 800)])
    articles, _ = feed_sources.read_source(source(mode="full"), DISCOVERED, fetcher_for(Site({"https://wire.example/feed": (200, feed)})), NOW, NOW - timedelta(hours=48))
    assert "basis" not in articles[0] and len(articles[0]["description"]) == 800


def test_old_items_are_left_out():
    old = (NOW - timedelta(days=5)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    feed = rss([("Old", "https://wire.example/o", old, "s"), ("New", "https://wire.example/n", RECENT, "s")])
    articles, _ = feed_sources.read_source(source(), DISCOVERED, fetcher_for(Site({"https://wire.example/feed": (200, feed)})), NOW, NOW - timedelta(hours=48))
    assert [a["title"] for a in articles] == ["New"]


def test_a_broken_stored_address_triggers_a_logged_rediscovery_and_leaves_the_file_alone():
    home = '<html><link rel="alternate" type="application/rss+xml" href="/new/feed.xml"></html>'
    site = Site({"https://wire.example/feed": (404, b""), "https://wire.example/": (200, home.encode()), "https://wire.example/new/feed.xml": (200, FEED)})
    stored, messages = copy.deepcopy(DISCOVERED), []
    articles, report = feed_sources.read_source(source(), stored, fetcher_for(site), NOW, NOW - timedelta(hours=48), relogger=messages.append)
    assert report["rediscovered"] is True and len(articles) == 2 and any("stopped working" in message for message in messages)
    assert stored == DISCOVERED, "only the probe workflow's verified output may rewrite config/feeds_discovered.json"


def test_a_source_that_cannot_be_read_reports_its_status_and_reason_instead_of_vanishing():
    site = Site({"https://wire.example/": (403, b"")})
    articles, report = feed_sources.read_source(source(), {}, fetcher_for(site), NOW, NOW - timedelta(hours=48))
    assert articles == [] and report["status"] == "disabled_blocked" and "403" in report["error"]


def test_sec_edgar_items_are_filtered_to_the_agreed_item_numbers():
    sec = source(source_type="exchange", official="true", tier="1", mode="full",
                 notes=json.dumps({"discovery_urls": ["https://wire.example/"], "cik": "0000027904", "edgar_items": ["2.02", "7.01", "8.01"]}))
    feed = rss([("8-K - Delta Air Lines", "https://wire.example/e1", RECENT, "Item 2.02: Results of Operations Item 9.01"),
                ("8-K - Delta Air Lines", "https://wire.example/e2", RECENT, "Item 5.02: Departure of Directors")])
    articles, _ = feed_sources.read_source(sec, DISCOVERED, fetcher_for(Site({"https://wire.example/feed": (200, feed)})), NOW, NOW - timedelta(hours=48))
    assert [a["link"] for a in articles] == ["https://wire.example/e1"]


# --- the pipeline ---------------------------------------------------------------------------------------------------------

def test_the_pipeline_reads_catalog_feeds_and_reports_every_source(monkeypatch):
    rows = [row("Wire Example"), row("Blocked Wire", status="disabled_blocked", active="0", reason="403 on /"), row("Legacy Feed")]
    monkeypatch.setattr(source_catalog, "read_rows", lambda path=None: rows)
    monkeypatch.setattr(feed_sources, "load_discovered", lambda path=None: DISCOVERED)
    monkeypatch.setattr(_engine, "get_builtin_source_records", lambda max_hours=48: [{"name": "Legacy Feed", "url": "https://legacy.example/"}])
    monkeypatch.setattr(_engine, "get_rss_sources", lambda max_hours=48: [])
    site = Site({"https://wire.example/feed": (200, FEED)})
    monkeypatch.setattr(_engine.feed_discovery, "PoliteFetcher", lambda **kw: _make_fetcher(site))
    monkeypatch.setattr(entities.EntityIndex, "from_csv", classmethod(lambda cls, *a, **k: entities.EntityIndex.__new__(cls)))
    monkeypatch.setattr(feed_sources, "filter_for_aviation", lambda items, index: (items[:1], len(items) - 1))
    report = {}
    articles = _engine.fetch_rss_items(report=report)
    assert [a["title"] for a in articles] == ["Airline X orders 50 jets from Airbus"]
    assert report["Wire Example"]["articles"] == 1 and report["Wire Example"]["filtered_out"] == 1 and report["Wire Example"]["articles_24h"] == 1
    assert report["Blocked Wire"] == {"status": "disabled_blocked", "error": "403 on /", "articles": 0}


def _make_fetcher(site):
    return REAL_FETCHER(fetch=site, sleep=lambda s: None)


def test_a_candidate_story_from_a_headline_only_source_has_no_published_lead():
    article = feed_sources.article_from_item(fd.Item("Carrier opens base in Lisbon", "https://wire.example/a1", NOW, "The carrier said on Friday that it will open a base."), source())
    story = _engine.build_candidate_story(article)
    assert story["basis"] == "headline_only" and story["lead"] == "" and story["source_description"].startswith("The carrier said")


def test_the_api_never_serves_a_headline_only_summary(monkeypatch):
    story = {"story_id": "story-1", "id": "story-1", "headline": "H", "relevance_score": 70, "basis": "headline_only", "source_description": "publisher summary text",
             "narrative_status": "pending", "first_seen_at": story_lifecycle.to_iso(NOW), "published_at_iso": story_lifecycle.to_iso(NOW),
             "original_source": {"url": "https://wire.example/a1", "title": "H", "source_name": "Wire Example"}, "sources": [{"name": "Wire Example", "url": "https://wire.example/a1", "title": "H"}]}
    day = {"date": "2026-10-17", "status": "ok", "stories": [story], "market": {}, "last_pipeline_run_at": story_lifecycle.to_iso(NOW)}
    monkeypatch.setattr(briefing_store, "read_json", lambda path: copy.deepcopy(day) if path == briefing_store.latest_path() else None)
    monkeypatch.setattr(story_lifecycle, "utc_now", lambda: NOW)
    served = _engine.get_ready_briefing("daily")["stories"][0]
    assert served["source_description"] == "" and day["stories"][0]["source_description"] == "publisher summary text"


# --- the narrative boundary ------------------------------------------------------------------------------------------------

def test_the_prompt_and_the_request_mark_headline_only_items():
    assert 'basis "headline_only"' in narrative.SYSTEM_PROMPT and "Do not add any number" in narrative.SYSTEM_PROMPT
    items = narrative.build_request_items([{"story_id": "s1", "basis": "headline_only", "original_source": {"title": "t"}, "source_description": "d"}], 500)
    assert items[0]["basis"] == "headline_only"


def test_figures_the_model_was_not_given_are_removed():
    fields = {"headline": "Airline X orders 120 jets", "lead": "The carrier ordered 50 jets. It plans to grow in 2027.", "why_it_matters": "Capacity rises by 12 percent.",
              "detailed_analysis": ["Order of 50 jets confirmed.", "Deliveries start in 2029."], "data_points": ["50 jets", "120 jets"], "strategic_impact": "Fleet renewal.",
              "market_exposure": [{"carrier": "Airline X", "impact": "Positive", "details": "Adds 30 aircraft."}, {"carrier": "Airbus", "impact": "Positive", "details": "Wins the order."}]}
    clean, removed = narrative.sanitize_headline_only(fields, "Airline X orders 50 jets from Airbus The carrier confirmed the order.")
    assert clean["lead"] == "The carrier ordered 50 jets." and clean["why_it_matters"] == ""
    assert clean["detailed_analysis"] == ["Order of 50 jets confirmed."] and clean["data_points"] == ["50 jets"]
    assert clean["market_exposure"][0]["details"] == "" and clean["market_exposure"][1]["details"] == "Wins the order."
    assert removed >= 5


def test_thousands_separators_do_not_count_as_new_numbers():
    known = narrative.grounded_numbers("Order for 1,200 aircraft")
    assert not narrative.has_ungrounded_number("1.200 aircraft", known) and narrative.has_ungrounded_number("1,300 aircraft", known)


def test_a_headline_only_story_is_narrated_without_invented_numbers_and_forgets_the_summary():
    story = {"story_id": "story-h", "relevance_score": 70, "narrative_status": "pending", "basis": "headline_only", "headline": "Airline X orders jets",
             "original_source": {"title": "Airline X orders 50 jets from Airbus", "source_name": "Wire Example"}, "source_description": "Confirmed Friday.",
             "source_count": 1, "first_seen_at": "2026-10-17T08:00:00+00:00"}

    def post(items):
        produced = [{"story_id": "story-h", "headline": "Airline X orders 90 jets", "lead": "Airline X ordered 50 jets from Airbus.", "detailed_analysis": ["Order confirmed.", "Worth 9 billion dollars."],
                     "data_points": ["50 jets", "9 billion dollars"], "strategic_impact": "Fleet growth.", "market_exposure": [], "why_it_matters": "Capacity grows 20 percent."}]
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({"stories": produced})}]}}]}

    report = narrative.fill_pending([story], "key", 800, post=post, sleep=lambda s: None, now=NOW)
    assert story["narrative_status"] == "done" and story["basis"] == "headline_only"
    assert story["headline"] == "Airline X orders 50 jets from Airbus", "an invented figure in the headline falls back to the source title"
    assert story["data_points"] == ["50 jets"] and story["detailed_analysis"] == ["Order confirmed."] and story["why_it_matters"] == ""
    assert story["source_description"] == "" and report["numbers_removed"] >= 4


def test_a_full_mode_story_keeps_its_description_and_figures():
    story = {"story_id": "story-f", "relevance_score": 70, "narrative_status": "pending", "headline": "x", "original_source": {"title": "t", "source_name": "Wire"},
             "source_description": "details", "source_count": 1, "first_seen_at": "2026-10-17T08:00:00+00:00"}

    def post(items):
        produced = [{"story_id": "story-f", "headline": "h", "lead": "Ordered 70 jets.", "detailed_analysis": ["a"], "data_points": ["70 jets"], "strategic_impact": "s", "market_exposure": [], "why_it_matters": "w"}]
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({"stories": produced})}]}}]}

    narrative.fill_pending([story], "key", 800, post=post, sleep=lambda s: None, now=NOW)
    assert story["data_points"] == ["70 jets"] and story["source_description"] == "details"


def test_a_headline_only_summary_is_never_written_to_the_archive(tmp_path, monkeypatch):
    from scripts import run_pipeline
    story = {"id": "story-h", "story_id": "story-h", "section": "Route news", "region_section": "Europe", "headline": "Airline X opens base", "event_type": None, "relevance_score": 70,
             "narrative_status": "pending", "lead": "", "basis": "headline_only", "source_description": "publisher summary that must not be stored", "source_count": 1,
             "original_source": {"url": "https://wire.example/h", "title": "Airline X opens base", "source_name": "Wire Example"},
             "sources": [{"name": "Wire Example", "url": "https://wire.example/h", "title": "Airline X opens base"}], "published_at_iso": story_lifecycle.to_iso(NOW)}
    low = dict(story, story_id="story-low", id="story-low", relevance_score=36, original_source={"url": "https://wire.example/low", "title": "Low band item", "source_name": "Wire Example"},
               sources=[{"name": "Wire Example", "url": "https://wire.example/low", "title": "Low band item"}], headline="Low band item")
    monkeypatch.setattr(_engine, "collect_run", lambda: {"stories": [copy.deepcopy(story), copy.deepcopy(low)], "articles": 5, "candidates": 2, "market": {"status": "ok", "items": [], "events": []}, "source_report": {}})
    seen = []

    def narrate(stories, api_key, limit, now=None):
        seen.extend((s["story_id"], s.get("source_description")) for s in stories)
        for s in stories:
            s["narrative_status"] = "done"
        return {"calls": 1, "narrated": len(stories), "pending": 0, "error": ""}

    run_pipeline.run(out_dir=tmp_path, now=NOW, api_key="k", narrate=narrate)
    archive = json.loads(next((tmp_path / "briefings").glob("2026-*.json")).read_text(encoding="utf-8"))
    assert ("story-h", "publisher summary that must not be stored") in seen, "the model still receives the summary in memory"
    assert all(item["source_description"] == "" for item in archive["stories"]), "nothing of the publisher's text reaches the archive file"


def test_a_stored_address_is_read_even_if_one_item_is_incomplete():
    # a dated-link page or a feed with one malformed item: strict verification at storage time, lenient reading afterwards
    feed = (f'<?xml version="1.0"?><rss version="2.0"><channel><item><title>Airline X opens base</title><link>https://wire.example/a1</link><pubDate>{RECENT}</pubDate></item>'
            f'<item><title>No date on this one</title><link>https://wire.example/a2</link></item></channel></rss>').encode()
    site = Site({"https://wire.example/feed": (200, feed)})
    articles, report = feed_sources.read_source(source(), DISCOVERED, fetcher_for(site), NOW, NOW - timedelta(hours=48))
    assert [a["title"] for a in articles] == ["Airline X opens base"] and report["rediscovered"] is False and report["status"] == "active"
    assert site.log == ["https://wire.example/feed"], "no re-discovery was needed"
