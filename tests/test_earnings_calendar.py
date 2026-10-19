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
    assert "renderEarningsCalendar" in html
    assert "calendar-section" in html
    assert "Havacılık Bilanço &amp; Trafik Takvimi" in html
    assert "ticker-cal-btn" in html
