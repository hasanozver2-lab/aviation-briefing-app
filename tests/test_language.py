import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from api import _engine, language, narrative, story_lifecycle

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
CONFIG = language.load_language_config()
PROJECT_DIR = Path(__file__).resolve().parents[1]


def story(sources, narrative_status="done", narrative_language=None, headline="Headline"):
    entries = [{"name": name, "url": f"https://example.com/{index}", "title": title, "language": lang} for index, (name, title, lang) in enumerate(sources)]
    item = {
        "story_id": "story-test", "id": "story-test", "headline": headline, "relevance_score": 70, "narrative_status": narrative_status, "source_count": len(entries),
        "sources": entries, "original_source": {"source_name": entries[0]["name"], "title": entries[0]["title"], "url": entries[0]["url"]},
        "source_description": "d", "first_seen_at": "2026-10-16T08:00:00+00:00",
    }
    if narrative_language:
        item["narrative_language"] = narrative_language
    return item


# --- source and article language -------------------------------------------------------------------------------

def test_the_language_column_exists_for_every_source_and_is_tr_or_en():
    languages = language.source_languages()
    import csv
    names = [row["name"] for row in csv.DictReader((PROJECT_DIR / "config" / "sources.csv").open(encoding="utf-8-sig"))]
    assert set(names) == set(languages) and set(languages.values()) <= {"tr", "en"}
    assert languages["HavaHaber"] == "tr" and languages["Simple Flying"] == "en"


def test_a_turkish_source_gives_turkish_and_an_english_source_english_whatever_the_text():
    assert language.article_language("HavaHaber", "Pegasus new route announced") == "tr"
    assert language.article_language("Simple Flying", "Türk Hava Yolları yeni uçak teslim aldı") == "en"


def test_an_unknown_source_falls_back_to_deterministic_text_detection():
    assert language.article_language("Unknown Blog", "THY yeni uçak teslim aldı ve filoya kattı") == "tr"
    assert language.article_language("Unknown Blog", "Lufthansa adds a new route to Tokyo") == "en"
    assert language.article_language("Unknown Blog", "") == "en"


@pytest.mark.parametrize("text, expected", [
    ("İstanbul Havalimanı'nda uçuşlar normale döndü", "tr"),
    ("Pegasus yeni hatlar için bir anlaşma imzaladı", "tr"),
    ("Delta launches a new daily flight to Reykjavík", "en"),          # an accent alone is not Turkish
    ("Lufthansa orders 20 aircraft from Airbus", "en"),
])
def test_text_detection(text, expected):
    assert language.detect_language(text) == expected


def test_fetched_articles_carry_a_language_field():
    source = (PROJECT_DIR / "api" / "_engine.py").read_text(encoding="utf-8")
    assert '"language": language.article_language(source_name' in source


# --- stories ------------------------------------------------------------------------------------------------------

def test_all_turkish_sources_make_a_turkish_story():
    item = story([("HavaHaber", "THY yeni uçak aldı", "tr"), ("Tolga Özbek Havacılık", "THY filoya katıldı", "tr")])
    assert language.story_language(item) == "tr"


def test_an_english_source_makes_an_english_story():
    assert language.story_language(story([("Simple Flying", "THY takes a new aircraft", "en")])) == "en"


def test_a_mixed_cluster_is_english():
    item = story([("HavaHaber", "THY yeni uçak aldı", "tr"), ("Simple Flying", "THY takes a new aircraft", "en")])
    assert language.story_language(item) == "en"


def test_sources_stored_before_languages_existed_are_looked_up_by_name():
    item = story([("HavaHaber", "x", None)])
    assert language.story_language(item) == "tr"
    assert language.story_language(story([("Simple Flying", "x", None)])) == "en"


def test_the_cluster_rule_lives_in_the_config_only():
    assert CONFIG["story_rule"] == {"turkish_only_language": "tr", "otherwise": "en"}
    assert language.story_language_from(["tr", "tr"], CONFIG) == "tr" and language.story_language_from(["tr", "en"], CONFIG) == "en"
    assert language.story_language_from([], CONFIG) == "en"
    flipped = {**CONFIG, "story_rule": {"turkish_only_language": "tr", "otherwise": "tr"}}
    assert language.story_language_from(["tr", "en"], flipped) == "tr"


def test_enrichment_and_the_api_give_every_story_a_language():
    now = NOW
    item = story([("HavaHaber", "THY yeni uçak aldı", "tr")])
    item["published_at_iso"] = story_lifecycle.to_iso(now)
    item["first_seen_at"] = story_lifecycle.to_iso(now)
    day = {"stories": [item]}
    story_lifecycle.present_stories(day, now)
    assert day["stories"][0]["language"] == "tr"


def test_a_story_that_gains_an_english_source_changes_language_on_read():
    item = story([("HavaHaber", "THY yeni uçak aldı", "tr")])
    item["first_seen_at"] = story_lifecycle.to_iso(NOW)
    day = {"stories": [item]}
    story_lifecycle.present_stories(day, NOW)
    assert day["stories"][0]["language"] == "tr"
    item["sources"].append({"name": "Simple Flying", "url": "https://example.com/en", "title": "THY new aircraft", "language": "en"})
    story_lifecycle.present_stories(day, NOW)
    assert day["stories"][0]["language"] == "en"


# --- narrative ---------------------------------------------------------------------------------------------------

class Llm:
    def __init__(self):
        self.requests = []

    def post(self, items):
        self.requests.append(items)
        produced = [{"story_id": i["story_id"], "headline": f"H {i['target_language']}", "lead": "L", "detailed_analysis": ["a"], "data_points": ["600 engines"],
                     "strategic_impact": "s", "market_exposure": [], "why_it_matters": "w"} for i in items]
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({"stories": produced})}]}}]}


def run(stories, llm=None):
    llm = llm or Llm()
    report = narrative.fill_pending(stories, "key", 800, post=llm.post, sleep=lambda s: None, now=NOW)
    return report, llm


def test_the_request_names_the_target_language_per_story():
    turkish = story([("HavaHaber", "THY yeni uçak aldı", "tr")], narrative_status="pending")
    english = story([("Simple Flying", "THY takes a new aircraft", "en")], narrative_status="pending")
    english["story_id"] = "story-en"
    _, llm = run([turkish, english])
    sent = {item["story_id"]: item["target_language"] for item in llm.requests[0]}
    assert sent == {"story-test": "tr", "story-en": "en"}


def test_the_prompt_asks_for_the_target_language_exact_numbers_and_natural_turkish():
    prompt = narrative.SYSTEM_PROMPT
    assert "target_language" in prompt and "never changed, converted, rounded" in prompt
    assert "ASK, RPK, doluluk oranı, yield" in prompt and "impact stays one of the English labels" in prompt


def test_the_narrative_language_is_stored_with_the_narrative():
    pending = story([("HavaHaber", "x", "tr")], narrative_status="pending")
    run([pending])
    assert pending["narrative_status"] == "done" and pending["narrative_language"] == "tr"


def test_a_narrative_in_the_wrong_language_is_regenerated_once():
    old_english = story([("HavaHaber", "x", "tr")], narrative_status="done")              # written before languages existed -> English
    report, llm = run([old_english])
    assert report["rewritten"] == 1 and report["narrated"] == 0 and len(llm.requests) == 1
    assert old_english["narrative_language"] == "tr" and old_english["headline"] == "H tr"
    report, llm = run([old_english])                                                      # second run: nothing left to do
    assert report["calls"] == 0 and llm.requests == []


def test_a_narrative_in_the_right_language_is_left_alone():
    done = story([("Simple Flying", "x", "en")], narrative_status="done", narrative_language="en")
    legacy_english = story([("Simple Flying", "x", "en")], narrative_status="done")        # no narrative_language: English by definition
    report, llm = run([done, legacy_english])
    assert report["calls"] == 0 and llm.requests == []


def test_when_a_story_changes_language_it_is_regenerated():
    item = story([("HavaHaber", "x", "tr")], narrative_status="done", narrative_language="tr")
    item["sources"].append({"name": "Simple Flying", "url": "https://example.com/en", "title": "t", "language": "en"})
    report, llm = run([item])
    assert report["rewritten"] == 1 and item["narrative_language"] == "en" and llm.requests[0][0]["target_language"] == "en"


def test_a_failed_rewrite_keeps_the_old_narrative_and_the_quota_rules_still_apply():
    old = story([("HavaHaber", "x", "tr")], narrative_status="done")
    old["headline"] = "Old English headline"

    def refuse(items):
        import urllib.error
        raise urllib.error.HTTPError("u", 429, "rate", {}, None)

    report = narrative.fill_pending([old], "key", 800, post=refuse, sleep=lambda s: None, now=NOW)
    assert old["headline"] == "Old English headline" and old["narrative_status"] == "done" and report["error"]
    many = [dict(story([("HavaHaber", "x", "tr")]), story_id=f"s{i}") for i in range(40)]
    _, llm = run(many)
    assert len(llm.requests) <= narrative.load_narrative_config()["max_calls_per_run"]


def test_new_stories_are_narrated_before_language_rewrites():
    rewrite = story([("HavaHaber", "x", "tr")], narrative_status="done")
    fresh = story([("Simple Flying", "x", "en")], narrative_status="pending")
    fresh["story_id"] = "story-fresh"
    fresh["relevance_score"] = 10
    order = [i["story_id"] for i in run([rewrite, fresh])[1].requests[0]]
    assert order == ["story-fresh", "story-test"]


# --- uppercase and the page ------------------------------------------------------------------------------------------

def test_turkish_dotted_and_dotless_i_are_lowered_correctly_for_detection():
    assert language.turkish_lower("İSTANBUL IŞIK") == "istanbul ışık"
    assert language.detect_language("İSTANBUL HAVALİMANI ve bir uçuş") == "tr"


def test_the_page_marks_story_text_with_its_language_and_ui_labels_as_english():
    html = (PROJECT_DIR / "public" / "index.html").read_text(encoding="utf-8")
    assert 'function langOf(story) { return story && story.language === "tr" ? "tr" : "en"; }' in html
    for needle in ('<h3 lang="${langOf(s)}">', '<h2 lang="${langOf(lead)}">', '<h1 tabindex="-1" lang="${lang}">', '<p class="art-lead" lang="${lang}">'):
        assert needle in html, needle
    # kicker tags and eyebrows are UI text: without lang="en" a Turkish ancestor would turn "Critical" into "CRİTİCAL"
    assert 'lang="en" class="eyebrow"' in html and '<span lang="en" class="new">New</span>' in html
    assert 'lang="en" class="group-head eyebrow"' in html


def test_the_fonts_request_covers_the_latin_extended_turkish_letters():
    html = (PROJECT_DIR / "public" / "index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis.com/css2" in html and "Newsreader" in html and "IBM+Plex+Sans" in html     # css2 serves latin-ext by unicode-range


@pytest.fixture(scope="module")
def browser_page():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="msedge")
        except Exception:
            pytest.skip("no browser available")
        page = browser.new_page()
        yield page
        browser.close()


def test_css_uppercase_follows_turkish_rules_only_inside_lang_tr(browser_page):
    browser_page.set_content(
        '<style>p{text-transform:uppercase}</style>'
        '<p id="tr" lang="tr">ışık istanbul havalimanı</p><p id="en" lang="en">ışık istanbul</p>'
        '<div lang="tr"><span id="label" lang="en">critical</span></div>'
    )
    assert browser_page.inner_text("#tr") == "IŞIK İSTANBUL HAVALİMANI"
    assert browser_page.inner_text("#en") == "IŞIK ISTANBUL"
    browser_page.add_style_tag(content="span{text-transform:uppercase}")
    assert browser_page.inner_text("#label") == "CRITICAL", "an English label inside a Turkish card must not get a dotted capital I"
