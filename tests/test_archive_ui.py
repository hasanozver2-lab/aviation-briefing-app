"""Optional real-browser regression checks; no publisher/network requests are made."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


playwright = pytest.importorskip("playwright.sync_api")
PAGE_HTML = (Path(__file__).resolve().parents[1] / "public" / "index.html").read_text(encoding="utf-8")
TODAY = (datetime.now(timezone.utc) + timedelta(hours=3)).date()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()


def story(identity, headline, **extra):
    return {"story_id": identity, "headline": headline, "level": "important", "relevance_score": 55,
            "region_section": "Europe", "narrative_status": "done", "language": "en",
            "why_it_matters": "Published evidence", "sources": [], "badges": ["new", "breaking"],
            "original_source": {"source_name": "Official", "url": "https://example.com/" + identity}, **extra}


def payload(date, stories):
    return {"date": date, "date_str": date, "stories": stories, "status": "ok", "market": {},
            "last_pipeline_run_at": date + "T08:00:00+03:00"}


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as engine:
        try:
            instance = engine.chromium.launch(channel="msedge", headless=True)
        except playwright.Error:
            pytest.skip("Optional browser tests require an installed Microsoft Edge")
        yield instance
        instance.close()


@pytest.fixture(params=[{"width": 390, "height": 844}, {"width": 1440, "height": 1000}], ids=["phone", "desktop"])
def archive_page(browser, request):
    page = browser.new_page(viewport=request.param)
    errors, requests = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    today = payload(TODAY.isoformat(), [story("today", "Today's airline story"),
                                       story("report", "Strategic report", is_strategic_report=True)])
    today["verification_pending_count"] = 1
    today["verification_pending_stories"] = [{"story_id": "pending", "headline": "Publisher headline <unsafe>",
                                              "reported_source": "Trade press", "language": "en",
                                              "lead": "Unsupported old analysis", "badges": ["breaking"],
                                              "original_source": {"url": "https://news.google.com/fake"}}]
    archived = payload(YESTERDAY, [story("old", "Previously collected airline story"),
                                  story("low", "Lower-score archived story", level="low", listed=False)])

    def handle(route):
        parsed = urlparse(route.request.url)
        if parsed.hostname != "archive.test":
            route.abort()
            return
        if parsed.path == "/api/briefing":
            query = parse_qs(parsed.query)
            requests.append(query)
            if "date" in query and query["date"][0] != YESTERDAY:
                route.fulfill(status=404, json={"error": "no archive"})
            else:
                route.fulfill(json=archived if "date" in query else today)
            return
        route.fulfill(content_type="text/html; charset=utf-8", body=PAGE_HTML)

    page.route("**/*", handle)
    yield page, errors, requests
    page.close()


def test_archive_loads_low_band_and_story_details_without_live_badges(archive_page):
    page, errors, requests = archive_page
    page.goto("https://archive.test/", wait_until="networkidle")
    page.locator('[data-page="archive"]').click()
    playwright.expect(page.locator("#archive-status")).to_have_text("2 stories collected for this day.")
    assert {"date": [YESTERDAY], "include_low": ["1"]} in requests
    assert page.locator('#content [data-open="low"]').count() == 1
    assert page.locator("#content .breaking, #content .new").count() == 0
    assert page.locator("#market").is_hidden()
    page.locator('#content [data-open="old"]').first.click()
    playwright.expect(page.locator("#art-body h1")).to_have_text("Previously collected airline story")
    assert "archive=" + YESTERDAY in page.url
    assert page.locator("#art-body .breaking, #art-body .new").count() == 0
    page.locator("#art-back").click()
    playwright.expect(page.locator("#article")).to_have_attribute("aria-hidden", "true")
    assert not errors


def test_missing_day_and_return_to_today(archive_page):
    page, errors, requests = archive_page
    page.goto("https://archive.test/", wait_until="networkidle")
    page.locator('[data-page="archive"]').click()
    playwright.expect(page.locator("#archive-status")).to_contain_text("2 stories")
    page.locator("#archive-prev").click()
    playwright.expect(page.locator("#archive-status")).to_have_text("No archive was saved for this date.")
    assert page.locator('#content [data-open="old"]').count() == 0
    page.locator('[data-page="briefing"]').click()
    playwright.expect(page.locator('#content [data-open="today"]').first).to_be_visible()
    assert "archive=" not in page.url
    assert page.locator("#archive-controls").is_hidden()
    page.locator('[data-page="reports"]').click()
    playwright.expect(page.locator('#content [data-open="report"]')).to_be_visible()
    assert not errors


def test_archive_direct_link_and_late_today_response_do_not_change_archive(archive_page):
    page, errors, requests = archive_page
    page.goto("https://archive.test/?archive=" + YESTERDAY + "#old", wait_until="networkidle")
    playwright.expect(page.locator("#art-body h1")).to_have_text("Previously collected airline story")
    page.evaluate("applyPolled({stories: [{story_id: 'intruder', headline: 'Wrong day'}]})")
    assert page.locator('#content [data-open="intruder"]').count() == 0
    page.locator("#art-back").click()
    playwright.expect(page.locator("#article")).to_have_attribute("aria-hidden", "true")
    playwright.expect(page.locator("#counts")).to_have_text("2 archived stories")
    page.locator("#archive-next").click()
    playwright.expect(page.locator("#archive-next")).to_be_disabled()
    assert not errors


def test_archive_controls_fit_viewport(archive_page):
    page, errors, requests = archive_page
    page.goto("https://archive.test/?archive=" + YESTERDAY, wait_until="networkidle")
    playwright.expect(page.locator("#archive-status")).to_contain_text("2 stories")
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    assert not errors


def test_unchecked_headlines_are_normal_clickable_rows_without_unsupported_analysis(archive_page):
    page, errors, requests = archive_page
    page.goto("https://archive.test/", wait_until="networkidle")
    row = page.locator('#content [data-open="pending"]')
    playwright.expect(row).to_be_visible()
    playwright.expect(row).to_contain_text("Publisher headline <unsafe>")
    playwright.expect(row).to_contain_text("Source not checked")
    assert row.locator("unsafe, .breaking, .new").count() == 0
    assert page.locator("#verification-pending").count() == 0
    playwright.expect(page.locator("#counts")).to_have_text("2 stories · 1 breaking")
    row.click()
    playwright.expect(page.locator("#art-body h1")).to_have_text("Publisher headline <unsafe>")
    assert "Unsupported old analysis" not in page.locator("#art-body").inner_text()
    assert page.locator("#art-body a, #art-body .breaking").count() == 0
    page.locator("#art-back").click()
    page.locator('[data-page="reports"]').click()
    assert page.locator('#content [data-open="pending"]').count() == 0
    page.locator('[data-page="archive"]').click()
    playwright.expect(page.locator("#archive-status")).to_contain_text("2 stories")
    assert page.locator('#content [data-open="pending"]').count() == 0
    assert not errors


def test_unchecked_headlines_join_polling_and_deduplicate_when_verified(archive_page):
    page, errors, requests = archive_page
    page.goto("https://archive.test/", wait_until="networkidle")
    page.evaluate("""() => {
      window.scrollTo(0, 0);
      applyPolled({...state.data, verification_pending_stories: [
        ...state.data.verification_pending_stories,
        {story_id: 'new-unchecked', headline: 'Newly collected publisher title', reported_source: 'Official'}
      ]});
    }""")
    playwright.expect(page.locator('#content [data-open="new-unchecked"]')).to_be_visible()
    page.evaluate("""() => render({...state.data,
      stories: [...state.data.stories, {story_id: 'pending', headline: 'Confirmed publisher title',
        region_section: 'Europe', sources: [], badges: [], narrative_status: 'pending'}]
    })""")
    playwright.expect(page.locator('#content [data-open="pending"]')).to_have_count(1)
    playwright.expect(page.locator('#content [data-open="pending"]')).to_contain_text("Confirmed publisher title")
    assert not errors
