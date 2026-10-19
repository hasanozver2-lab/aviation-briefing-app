import copy

import pytest

from api import _engine, source_recovery, story_lifecycle

SELECTION = story_lifecycle.load_relevance_config()["selection"]
REDIRECT = "https://news.google.com/rss/articles/CBMiabc?oc=5"
DIRECT = "https://www.theaviationhub.co.uk/austrian-diverts"


def story(original=REDIRECT, sources=(), **extra):
    return {"headline": "Austrian diverts", "original_source": {"url": original, "title": "T", "source_name": "Reuters"},
            "sources": [{"name": name, "url": url, "title": "Title"} for name, url in sources], "source_count": len(sources), **extra}


def test_a_redirect_primary_link_is_replaced_by_the_first_direct_source():
    item = story(sources=[("Reuters", REDIRECT), ("The Aviation Hub", DIRECT)])
    assert story_lifecycle.ensure_direct_link(item, SELECTION)
    assert item["original_source"]["url"] == DIRECT and item["original_source"]["source_name"] == "The Aviation Hub"
    assert [entry["url"] for entry in item["sources"]] == [DIRECT] and item["source_count"] == 1


def test_unrecognized_redirect_or_missing_links_are_not_served():
    fake = story(original=REDIRECT, sources=[("Unknown Fake", REDIRECT)], original_source={"url": REDIRECT, "source_name": "Unknown Fake"})
    for item in (fake, story(original="", sources=[]), story(original="javascript:alert(1)"), story(original="not a url")):
        assert not story_lifecycle.has_direct_link(item, SELECTION)
        assert not story_lifecycle.ensure_direct_link(item, SELECTION)
    day = {"stories": [fake, story(original=DIRECT)]}
    assert story_lifecycle.drop_excluded(day) == 1 and day["stories"][0]["original_source"]["url"] == DIRECT


def test_recognized_publishers_with_redirect_links_are_served():
    for pub in ("Reuters", "Bloomberg", "Aviation Week", "ch-aviation", "The Wall Street Journal", "The New York Times"):
        item = story(original=REDIRECT, sources=[(pub, REDIRECT)], original_source={"url": REDIRECT, "source_name": pub})
        assert story_lifecycle.has_direct_link(item, SELECTION)
        assert story_lifecycle.ensure_direct_link(item, SELECTION)
        day = {"stories": [item]}
        assert story_lifecycle.drop_excluded(day) == 0


def test_a_direct_story_is_left_untouched():
    item = story(original=DIRECT, sources=[("A", DIRECT), ("B", "https://www.reuters.com/x")])
    before = copy.deepcopy(item)
    assert story_lifecycle.ensure_direct_link(item, SELECTION) and item == before


def test_the_waiting_headline_list_is_not_served_unless_switched_on(monkeypatch):
    config = source_recovery.load_config()
    assert config["serve_pending_titles"] is False
    assert "pending_titles(snapshot, pending_date) if source_recovery.load_config().get(\"serve_pending_titles\")" in open(_engine.__file__, encoding="utf-8").read()


def test_the_page_renders_the_original_source_link_for_every_story():
    page = open("public/index.html", encoding="utf-8").read()
    assert "Original source:" in page and "safeExternalUrl(src.url)" in page
