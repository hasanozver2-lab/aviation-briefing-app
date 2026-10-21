"""Tests for English-first global architecture and i18n (TR/EN) language switcher."""

from pathlib import Path
import json
import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
INDEX_PATH = PROJECT_DIR / "public" / "index.html"


def test_html_defaults_to_english():
    html = INDEX_PATH.read_text(encoding="utf-8")
    assert '<html lang="en">' in html
    assert 'id="lang-btn-en"' in html
    assert 'id="lang-btn-tr"' in html
    assert 'data-lang="en"' in html
    assert 'data-lang="tr"' in html
    assert 'data-drawer-lang="en"' in html
    assert 'data-drawer-lang="tr"' in html


def test_i18n_dictionary_contains_required_keys():
    html = INDEX_PATH.read_text(encoding="utf-8")
    assert "const I18N =" in html
    for key in (
        "nav_briefing",
        "nav_reports",
        "nav_airspace",
        "nav_fleet",
        "nav_calendar",
        "nav_archive",
        "traffic_title",
        "traffic_commercial_today",
        "airspace_intro_title",
        "fleet_intro_title",
        "cal_title",
        "reports_title",
        "mkt_crack_title",
        "btn_share",
    ):
        assert key in html, f"Missing i18n key: {key}"


def test_i18n_browser_interaction():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as engine:
        try:
            browser = engine.chromium.launch(channel="msedge", headless=True)
        except playwright.Error:
            pytest.skip("MS Edge not found")
            return

        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        from api import airspace_radar, earnings_calendar, fleet_watch

        radar_data = airspace_radar.load_radar(xml_text="")
        cal_data = earnings_calendar.load_calendar()
        fleet_data = fleet_watch.load_fleet_watch()

        mock_payload = {
            "date": "2026-10-21",
            "date_str": "2026-10-21",
            "stories": [],
            "status": "ok",
            "airspace_radar": radar_data,
            "earnings_calendar": cal_data,
            "fleet_watch": fleet_data,
            "market": {},
        }

        page.route("**/api/briefing*", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(mock_payload)
        ))

        index_url = INDEX_PATH.as_uri()
        page.goto(index_url, wait_until="domcontentloaded")
        page.wait_for_selector(".page-nav")

        # 1. Default load must be English
        assert page.is_visible("#lang-btn-en.active")
        briefing_nav_text = page.text_content('.page-btn[data-page="briefing"]')
        assert "Daily Briefing" in briefing_nav_text

        traffic_panel = page.text_content(".traffic-panel")
        assert "Commercial Flights Today" in traffic_panel

        # 2. Click TR button to switch to Turkish
        page.click("#lang-btn-tr")
        page.wait_for_timeout(200)

        assert page.is_visible("#lang-btn-tr.active")
        briefing_nav_text_tr = page.text_content('.page-btn[data-page="briefing"]')
        assert "Günlük Brifing" in briefing_nav_text_tr

        traffic_panel_tr = page.text_content(".traffic-panel")
        assert "Bugünkü Ticari Uçuş" in traffic_panel_tr

        # 3. Check Airspace Radar tab in Turkish
        page.click('.page-btn[data-page="airspace"]')
        page.wait_for_selector(".airspace-intro")
        airspace_text_tr = page.text_content(".airspace-intro")
        assert "Havacılık Güvenliği" in airspace_text_tr

        # 4. Switch back to English while on Airspace tab
        page.click("#lang-btn-en")
        page.wait_for_timeout(200)

        assert page.is_visible("#lang-btn-en.active")
        airspace_text_en = page.text_content(".airspace-intro")
        assert "Aviation Security" in airspace_text_en

        # 5. Check Calendar tab in English
        page.click('.page-btn[data-page="calendar"]')
        page.wait_for_selector(".calendar-intro")
        cal_text_en = page.text_content(".calendar-intro")
        assert "Aviation Earnings & Traffic Calendar" in cal_text_en

        # Check filter text in English
        filter_text_en = page.text_content('.filters')
        assert "All Events" in filter_text_en

        # 6. Check localStorage persistence
        saved_lang = page.evaluate("() => localStorage.getItem('aerobrief_lang')")
        assert saved_lang == "en"

        page.click("#lang-btn-tr")
        page.wait_for_timeout(100)
        saved_lang_tr = page.evaluate("() => localStorage.getItem('aerobrief_lang')")
        assert saved_lang_tr == "tr"

        # Screenshot proof of language switcher in action
        artifact_dir = Path("C:/Users/Lenovo/.gemini/antigravity/brain/5081c83a-eb09-4b62-8ac6-e2e267264392")
        if artifact_dir.exists():
            page.screenshot(path=str(artifact_dir / "i18n_language_toggle_tr.png"))
            page.click("#lang-btn-en")
            page.wait_for_timeout(100)
            page.screenshot(path=str(artifact_dir / "i18n_language_toggle_en.png"))

        browser.close()
        assert not errors, f"Browser errors: {errors}"
