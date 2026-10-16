import json
from datetime import date, timedelta

import pytest

from api import market_data

TODAY = date(2026, 10, 16)
USD_PER_EUR = 1.125
TRY_PER_EUR = 55.7


@pytest.fixture
def stored(tmp_path):
    database = tmp_path / "m.sqlite3"
    days = [TODAY - timedelta(days=offset) for offset in (3, 2, 1)]
    market_data.upsert_observations(database, {
        "brent_spot": [(d, 120.0 + i) for i, d in enumerate(days)],
        "us_gulf_coast_jet_fuel": [(d, 4.0 + i / 10) for i, d in enumerate(days)],
        "fx_usd_eur": [(d, 0.889) for d in days],
        "fx_usd_try": [(d, 49.5) for d in days],
    })
    return database


def series_ids(panel):
    return {item["series_id"] for item in panel["items"]}


def test_fx_display_is_off_by_default():
    assert market_data.display_fx() is False
    assert market_data.load_market_config()["market"]["display_fx"] is False


def test_with_the_switch_off_the_api_panel_has_only_fuel(stored):
    panel, _ = market_data.build_market_panel(stored)
    assert series_ids(panel) == {"brent_spot", "us_gulf_coast_jet_fuel", "jet_fuel_brent_crack_spread"}
    assert "European Central Bank" not in json.dumps(panel, ensure_ascii=False)


def test_ecb_data_is_still_stored_while_hidden(stored):
    assert market_data.load_observations(stored, "fx_usd_eur"), "collection continues; only the display is off"


def test_with_the_switch_on_fx_rows_return_with_a_unit_that_is_not_inverted(stored, monkeypatch):
    monkeypatch.setattr(market_data, "display_fx", lambda: True)
    panel, _ = market_data.build_market_panel(stored)
    items = {item["series_id"]: item for item in panel["items"]}
    assert {"fx_usd_eur", "fx_usd_try"} <= set(items)
    assert items["fx_usd_eur"]["unit"] == "EUR per USD" and items["fx_usd_try"]["unit"] == "TRY per USD"
    assert items["fx_usd_eur"]["value"] < 1 < items["fx_usd_try"]["value"], "EUR per USD is below 1, TRY per USD far above"


def test_the_value_matches_the_unit_computed_from_ecb_reference_rates(monkeypatch):
    csv_payload = "CURRENCY,TIME_PERIOD,OBS_VALUE\nUSD,2026-10-15,%s\nTRY,2026-10-15,%s\n" % (USD_PER_EUR, TRY_PER_EUR)
    monkeypatch.setattr(market_data, "_text_request", lambda url, **k: csv_payload)
    result = market_data.fetch_ecb_fx_series(TODAY - timedelta(days=5), TODAY)
    assert result["fx_usd_eur"][0][1] == pytest.approx(1 / USD_PER_EUR)             # EUR per 1 USD
    assert result["fx_usd_try"][0][1] == pytest.approx(TRY_PER_EUR / USD_PER_EUR)   # TRY per 1 USD
    unit = market_data.market_series_definitions()["fx_usd_eur"]["unit"]
    assert unit == "EUR per USD"


def test_fx_threshold_events_stay_in_the_database_but_not_in_the_panel(tmp_path, monkeypatch):
    database = tmp_path / "m.sqlite3"
    days = [TODAY - timedelta(days=offset) for offset in (3, 2, 1, 0)]
    market_data.upsert_observations(database, {"fx_usd_try": [(days[0], 40.0), (days[1], 40.0), (days[2], 40.0), (days[3], 44.0)]})
    monkeypatch.setattr(market_data, "fetch_ecb_fx_series", lambda s, e: {})
    monkeypatch.setattr(market_data, "fetch_fred_series", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    monkeypatch.setattr(market_data, "utc_now", lambda: market_data.datetime(2026, 10, 16, tzinfo=market_data.timezone.utc))
    hidden = market_data.refresh_market_data(database, end_date=TODAY)
    assert all(event["event_type"] != "fx_currency" for event in hidden["events"])
    monkeypatch.setattr(market_data, "display_fx", lambda: True)
    shown = market_data.refresh_market_data(database, end_date=TODAY)
    assert any(event["event_type"] == "fx_currency" for event in shown["events"])
