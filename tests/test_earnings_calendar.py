"""Tests for Aviation Earnings & Traffic Calendar (Bilanço & Trafik Takvimi)."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from api import earnings_calendar
from api import _engine


def test_classify_event_status():
    today = date(2026, 10, 20)
    # Today
    status, delta, badge_tr, badge_en = earnings_calendar.classify_event_status(date(2026, 10, 20), today)
    assert status == "TODAY"
    assert delta == 0
    assert "BUGÜN" in badge_tr

    # Within 3 days
    status, delta, badge_tr, badge_en = earnings_calendar.classify_event_status(date(2026, 10, 22), today)
    assert status == "THIS_WEEK"
    assert delta == 2
    assert "2 Gün Kaldı" in badge_tr

    # Within 7 days
    status, delta, badge_tr, badge_en = earnings_calendar.classify_event_status(date(2026, 10, 26), today)
    assert status == "THIS_WEEK"
    assert delta == 6
    assert "Bu Hafta" in badge_tr

    # Future (> 7 days)
    status, delta, badge_tr, badge_en = earnings_calendar.classify_event_status(date(2026, 11, 10), today)
    assert status == "UPCOMING"
    assert delta == 21
    assert "21 gün kaldı" in badge_tr

    # Past
    status, delta, badge_tr, badge_en = earnings_calendar.classify_event_status(date(2026, 10, 15), today)
    assert status == "REPORTED"
    assert delta < 0
    assert "Açıklandı" in badge_tr


def test_load_calendar_structure():
    fixed_now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
    cal = earnings_calendar.load_calendar(now=fixed_now)
    assert cal["status"] == "ok"
    assert cal["as_of"] == "2026-10-19"
    assert cal["total_events"] >= 8
    assert cal["upcoming_count"] >= 5
    assert "En yakın" in cal["highlight_tr"]
    assert "Next release" in cal["highlight_en"]
    assert len(cal["events"]) == cal["total_events"]


def test_turkish_and_global_entities_covered():
    cal = earnings_calendar.load_calendar()
    entities = [e["entity"] for e in cal["events"]]
    tickers = [e["ticker"] for e in cal["events"]]
    assert "Türk Hava Yolları" in entities
    assert "Pegasus Hava Yolları" in entities
    assert "Lufthansa Group" in entities
    assert "Airbus SE" in entities
    assert "THYAO" in tickers
    assert "PGSUS" in tickers


def test_event_types():
    cal = earnings_calendar.load_calendar()
    event_types = {e["event_type"] for e in cal["events"]}
    assert "financial_results" in event_types
    assert "traffic_report" in event_types


def test_ui_contract_crack_spread_and_calendar():
    html = (Path(__file__).resolve().parents[1] / "public" / "index.html").read_text(encoding="utf-8")
    assert "mkt-crack-card" in html
    assert "Jet Yakıtı Rafineri Marjı (Crack Spread)" in html
    assert "renderEarningsCalendarPage" in html
    assert 'data-page="calendar"' in html
    assert 'id="nav-calendar-count"' in html
    assert 'data-drawer-page="calendar"' in html
    assert 'id="drawer-calendar-count"' in html
    assert "data-calendar-filter" in html
    assert "calendar-list" in html
    assert "calendar-stats-grid" in html
    assert "Havacılık Bilanço &amp; Trafik Takvimi" in html
    # Calendar is now exclusively in its dedicated tab, not inside the market ticker
    assert "ticker-cal-btn" not in html


def test_calendar_browser_interaction():
    import json
    import pytest
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

        cal_data = earnings_calendar.load_calendar()
        mock_payload = {
            "date": "2026-10-21",
            "date_str": "2026-10-21",
            "stories": [],
            "status": "ok",
            "earnings_calendar": cal_data,
            "market": {},
        }

        page.route("**/api/briefing*", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(mock_payload)
        ))

        html_path = (Path(__file__).resolve().parents[1] / "public" / "index.html").as_uri()
        page.goto(html_path, wait_until="domcontentloaded")

        # Navigate to calendar page
        page.click('[data-page="calendar"]')
        page.wait_for_selector(".calendar-stats-grid")

        assert page.is_visible(".calendar-intro")
        assert page.is_visible(".calendar-stats-grid")
        assert page.is_visible(".calendar-list")

        cards = page.query_selector_all(".calendar-card")
        assert len(cards) >= 5

        # Check filter interaction
        page.click('[data-calendar-filter="TURKEY"]')
        turkey_cards = page.query_selector_all(".calendar-card")
        assert 0 < len(turkey_cards) < len(cards)

        # Screenshot artifact
        artifact_dir = Path("C:/Users/Lenovo/.gemini/antigravity/brain/5081c83a-eb09-4b62-8ac6-e2e267264392")
        if artifact_dir.exists():
            page.screenshot(path=str(artifact_dir / "calendar_tab_view.png"))

        browser.close()
        assert not errors, f"Browser console errors encountered: {errors}"
