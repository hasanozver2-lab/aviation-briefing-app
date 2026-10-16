import json
from datetime import date, timedelta

import pytest

from api import market_data

TODAY = date(2026, 10, 16)
SECRET = "k" * 32
BRENT = [(TODAY - timedelta(days=days), 120.0 + days) for days in (6, 5, 4, 3, 2)]
JET = [(TODAY - timedelta(days=days), 4.0 + days / 10) for days in (6, 5, 4, 3, 2)]
IDS = {"DCOILBRENTEU": BRENT, "DJFUELUSGULF": JET}
EIA_IDS = {"RBRTE": BRENT, "EER_EPJK_PF4_RGC_DPG": JET}


@pytest.fixture
def calls(monkeypatch):
    made = []
    monkeypatch.setattr(market_data, "fetch_ecb_fx_series", lambda start, end: {})

    def fred(series_id, api_key, start, end):
        made.append(("fred", series_id, bool(api_key)))
        return IDS[series_id]

    def eia(series_id, api_key, start, end):
        made.append(("eia", series_id, bool(api_key)))
        return EIA_IDS[series_id]

    monkeypatch.setattr(market_data, "fetch_fred_series", fred)
    monkeypatch.setattr(market_data, "fetch_eia_series", eia)
    return made


def refresh(tmp_path, **keys):
    return market_data.refresh_market_data(tmp_path / "m.sqlite3", end_date=TODAY, **keys)


def item(panel, series_id):
    return next(entry for entry in panel["items"] if entry["series_id"] == series_id)


def test_the_series_ids_are_the_agreed_fred_ones():
    series = market_data.load_market_config()["series"]
    assert series["brent_spot"]["fred_series"] == "DCOILBRENTEU"
    assert series["us_gulf_coast_jet_fuel"]["fred_series"] == "DJFUELUSGULF"


def test_without_an_eia_key_fred_serves_both_fuel_series_and_the_skip_is_recorded(tmp_path, calls):
    panel = refresh(tmp_path)
    assert [c[:2] for c in calls] == [("fred", "DCOILBRENTEU"), ("fred", "DJFUELUSGULF")]
    assert panel["skipped"] == ["EIA"] and panel["errors"] == [] and panel["fuel_provider"] == "fred"
    assert panel["status"] == "ok" and "missing_data_note" not in panel
    assert item(panel, "brent_spot")["source"] == "FRED (EIA)" and item(panel, "us_gulf_coast_jet_fuel")["source"] == "FRED (EIA)"


def test_a_fred_key_is_used_when_present_and_never_stored_in_the_panel(tmp_path, calls):
    panel = refresh(tmp_path, fred_api_key=SECRET)
    assert all(call[2] is True for call in calls)
    assert SECRET not in json.dumps(panel, ensure_ascii=False)


def test_eia_is_primary_when_its_key_exists_and_fred_is_not_called(tmp_path, calls):
    panel = refresh(tmp_path, eia_api_key="e", fred_api_key=SECRET)
    assert {c[0] for c in calls} == {"eia"} and panel["skipped"] == [] and panel["fuel_provider"] == "eia"
    assert item(panel, "brent_spot")["source"] == "U.S. Energy Information Administration"


def test_fred_is_the_fallback_when_eia_fails(tmp_path, calls, monkeypatch):
    monkeypatch.setattr(market_data, "fetch_eia_series", lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
    panel = refresh(tmp_path, eia_api_key="e")
    assert panel["errors"] == ["EIA: TimeoutError"] and panel["fuel_provider"] == "fred"
    assert item(panel, "brent_spot")["source"] == "FRED (EIA)"


def test_when_fred_is_down_too_the_pipeline_still_returns_a_panel(tmp_path, calls, monkeypatch):
    monkeypatch.setattr(market_data, "fetch_fred_series", lambda *a, **k: (_ for _ in ()).throw(ConnectionResetError()))
    panel = refresh(tmp_path)
    assert panel["status"] == "unavailable" or panel["status"] == "partial"
    assert panel["fuel_provider"] is None and "FRED" in panel["missing_data_note"] and panel["errors"] == ["FRED: ConnectionResetError"]


def test_as_of_is_the_real_observation_date_and_carried_forward_says_how_old(tmp_path, calls):
    panel = refresh(tmp_path)
    brent = item(panel, "brent_spot")
    assert brent["as_of"] == (TODAY - timedelta(days=2)).isoformat()
    assert brent["carried_forward"] is True and brent["age_days"] == 2


def test_the_crack_spread_keeps_the_42_rule_the_thresholds_and_names_its_source(tmp_path, calls):
    panel = refresh(tmp_path)
    spread = item(panel, "jet_fuel_brent_crack_spread")
    assert spread["value"] == pytest.approx(JET[-1][1] * 42 - BRENT[-1][1])
    assert spread["source"].startswith("FRED (EIA);") and "42" in spread["source"]
    thresholds = market_data.load_market_config()["thresholds"]
    assert thresholds["jet_fuel_weekly_change_pct"] == 5.0 and thresholds["crack_spread_standard_deviations"] == 1.5


# --- the fetchers ---------------------------------------------------------------------------------------------

def test_keyless_csv_parsing_skips_missing_days(monkeypatch):
    monkeypatch.setattr(market_data, "_text_request", lambda url, **k: "observation_date,DCOILBRENTEU\n2026-10-13,125.78\n2026-10-14,.\n2026-10-15,126.55\n")
    rows = market_data.fetch_fred_series_keyless("DCOILBRENTEU", date(2026, 10, 1), TODAY)
    assert rows == [(date(2026, 10, 13), 125.78), (date(2026, 10, 15), 126.55)]


def test_keyed_json_parsing_skips_missing_days(monkeypatch):
    payload = {"observations": [{"date": "2026-10-13", "value": "4.1"}, {"date": "2026-10-14", "value": "."}]}
    monkeypatch.setattr(market_data, "_json_request", lambda url, **k: payload)
    assert market_data.fetch_fred_series_with_key("DJFUELUSGULF", SECRET, date(2026, 10, 1), TODAY) == [(date(2026, 10, 13), 4.1)]


def test_a_failing_keyed_call_falls_back_to_keyless_without_leaking_the_key(monkeypatch):
    seen_urls = []

    def boom(url, **k):
        seen_urls.append(url)
        raise RuntimeError(url)   # a careless handler would carry the key in the message

    monkeypatch.setattr(market_data, "_json_request", boom)
    monkeypatch.setattr(market_data, "_text_request", lambda url, **k: "observation_date,X\n2026-10-15,1.5\n")
    assert market_data.fetch_fred_series("X", SECRET, date(2026, 10, 1), TODAY) == [(date(2026, 10, 15), 1.5)]
    assert SECRET in seen_urls[0]   # the key only ever travels in the request URL


def test_the_workflow_passes_the_fred_secret_by_reference_only():
    workflow = (market_data.BASE_DIR / ".github" / "workflows" / "briefing-pipeline.yml").read_text(encoding="utf-8")
    assert "FRED_API_KEY: ${{ secrets.FRED_API_KEY }}" in workflow
