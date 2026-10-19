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
    assert ".flash-alert-badge" in page and "⚡ FLASH ALERT" in page


def test_unshorten_google_news_url_resolves_to_direct_publisher():
    from api.urls import unshorten_google_news_url

    class MockResponse:
        def __init__(self, data):
            self.data = data.encode("utf-8") if isinstance(data, str) else data
        def read(self):
            return self.data
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_opener(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "rss/articles" in url:
            html = '<div data-n-a-sg="sig123" data-n-a-ts="1720000000"></div>'
            return MockResponse(html)
        if "batchexecute" in url:
            payload = ')]}\'\n[["wrb.fr","Fbv4je","[\\"garturlres\\",\\"https://www.reuters.com/business/aerospace/airline-test-story\\"]",null,null,null,"generic"]]'
            return MockResponse(payload)
        raise ValueError("Unexpected url: " + url)

    resolved = unshorten_google_news_url("https://news.google.com/rss/articles/CBMi12345", opener=mock_opener)
    assert resolved == "https://www.reuters.com/business/aerospace/airline-test-story"

    # Non-google URLs or missing tokens gracefully return the input URL unchanged
    assert unshorten_google_news_url("https://www.reuters.com/direct") == "https://www.reuters.com/direct"
    assert unshorten_google_news_url("") == ""


def test_flash_alerts_and_analyst_radar_classification():
    analyst_story = {
        "headline": "Boeing 737 MAX 10 Certification Flight Tests Advance",
        "original_source": {"url": "https://theaircurrent.com/aviation-safety/boeing-737-max-10-tests", "source_name": "The Air Current"},
        "source": "The Air Current",
    }
    social_story = {
        "headline": "Jon Ostrower reports unexpected FAA directive on MAX fleet",
        "original_source": {"url": "https://x.com/jonostrower/status/98765", "source_name": "Jon Ostrower on X"},
        "via_social": True,
    }
    standard_story = {
        "headline": "Airline announces quarterly financial report",
        "original_source": {"url": "https://www.reuters.com/business/quarterly-earnings", "source_name": "Reuters"},
    }
    assert story_lifecycle.is_flash_alert(analyst_story) is True
    assert story_lifecycle.is_flash_alert(social_story) is True
    assert story_lifecycle.is_flash_alert(standard_story) is False
