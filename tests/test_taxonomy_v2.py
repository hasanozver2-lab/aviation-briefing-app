import copy
from datetime import datetime, timezone

import pytest

from api import _engine, briefing_store, market_data, story_lifecycle

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
TYPES = market_data.load_taxonomy_config()["event_types"]
RELEVANCE = story_lifecycle.load_relevance_config()


def kind(title, description=""):
    result = market_data.classify_event_type(title, description)
    return result["event_type"] if result else None


# --- the agreed types and weights --------------------------------------------------------------------------

@pytest.mark.parametrize("name, weight", [
    ("airport_infrastructure", 0.5), ("partnerships_mna", 0.65), ("regulation_policy", 0.6), ("sustainability_saf", 0.45), ("workforce_hr", 0.3),
])
def test_new_types_exist_with_the_agreed_provisional_weights(name, weight):
    assert TYPES[name]["weight"] == weight


@pytest.mark.parametrize("title, expected", [
    ("Heathrow approves new terminal expansion", "airport_infrastructure"),
    ("Example Airlines and Sky Partner form a joint venture", "partnerships_mna"),
    ("EASA issues new airworthiness directive for engines", "regulation_policy"),
    ("ReFuelEU sustainable aviation fuel mandate here to stay", "sustainability_saf"),
    ("Emirates turns to Manila for first pilot recruitment drive", "workforce_hr"),
    ("ATR delivers new ATR 72-600 to an island carrier", "fleet_orders"),
    ("Airline announces retirement of its last 747", "fleet_orders"),
    ("Carrier completes cabin retrofit of its A320 fleet", "fleet_orders"),
    ("Emirates brings travel rehearsal programme for autistic children", "community_csr"),
])
def test_new_and_widened_types_classify(title, expected):
    assert kind(title) == expected


def test_saf_no_longer_sits_under_fuel_energy_where_it_would_outrank_the_new_type():
    assert "SAF" not in TYPES["fuel_energy"]["terms"]
    assert kind("Airline signs SAF supply deal") == "sustainability_saf"


# --- exclusion lists run before typing -----------------------------------------------------------------------

@pytest.mark.parametrize("title", [
    "Israel signs deal for 12 Boeing AH-64E Apache attack helicopters, F-16 fighter jet partnership",
    "Air force announces partnership on F-35 sustainment agreement",
])
def test_defence_titles_never_get_a_guarded_type(title):
    assert kind(title) not in {"partnerships_mna", "fleet_orders", "regulation_policy", "workforce_hr"}


@pytest.mark.parametrize("title", [
    "Airline stock analyst upgrade after fleet retirement plan",
    "Why I'd buy airline shares after the merger",
])
def test_investment_commentary_never_gets_a_guarded_type(title):
    assert kind(title) not in {"partnerships_mna", "fleet_orders", "airport_infrastructure"}


def test_keep_terms_rescue_a_defence_looking_title_with_civil_context():
    assert kind("Airline and air force agree airport slot partnership at the new terminal") is not None


def test_unguarded_types_are_not_affected_by_the_typing_exclusion():
    assert kind("F-16 fighter jet crash kills pilot") == "safety_incident"


# --- the two noise cases found on real data ---------------------------------------------------------------------

def test_a_loyalty_co_brand_partnership_is_not_a_partnerships_mna_story():
    assert kind("Aeroplan Members Get Rewarded for Coveted Dining Reservations and Experiences via Expanded DINR Partnership") is None


def test_partnership_with_an_aviation_word_still_classifies():
    assert kind("Airline and airport operator announce partnership") == "partnerships_mna"
    assert kind("Airline acquires regional carrier in merger") == "partnerships_mna"


@pytest.mark.parametrize("title", [
    "MKE'den 3 adet daha elektrikli zırhlı personel taşıyıcı teslimatı",
    "Army takes delivery of armored vehicles",
    "Attack helicopter delivery completed ahead of schedule",
])
def test_armoured_vehicle_and_helicopter_deliveries_are_defence_not_fleet_orders(title):
    assert story_lifecycle.is_military_story({"headline": title, "entities": {}}, RELEVANCE["selection"])
    assert kind(title) != "fleet_orders"


# --- read-time filter ------------------------------------------------------------------------------------------------

def stored(title, event_type, score, tier=4, url=None, carriers=None):
    url = url or f"https://example.com/{abs(hash(title))}"
    story_id = story_lifecycle.stable_story_id(url)
    return {
        "id": story_id, "story_id": story_id, "headline": title, "event_type": event_type, "relevance_score": score,
        "narrative_status": "done", "lead": "l", "region_section": "Europe", "section": "Route news", "source_count": 1,
        "entities": {"carriers": carriers or [], "groups": []}, "first_seen_at": story_lifecycle.to_iso(NOW),
        "published_at_iso": story_lifecycle.to_iso(NOW),
        "original_source": {"url": url, "title": title, "source_name": "Wire", "tier": tier, "official": False},
        "sources": [{"name": "Wire", "url": url, "title": title}],
    }


def day_with(*stories):
    return {"date": "2026-10-16", "status": "ok", "stories": [copy.deepcopy(s) for s in stories], "market": {}, "mode": "daily"}


@pytest.fixture
def serve(monkeypatch):
    def _serve(day):
        files = {briefing_store.latest_path(): day}
        monkeypatch.setattr(briefing_store, "read_json", lambda path: copy.deepcopy(files.get(path)))
        monkeypatch.setattr(story_lifecycle, "utc_now", lambda: NOW)
        return day
    return _serve


def test_the_api_drops_stock_and_military_stories_that_an_older_run_archived(serve):
    day = serve(day_with(
        stored("Airline opens new route to Tokyo", "route_network_change", 70),
        stored("Boeing stock falls below $200 amid market sentiment.", "operations_disruption", 46.5, tier=3),
        stored("Claim of Six Russian Su-34 Bombers Damaged by Missile Strike", "geopolitics_airspace", 48.8),
    ))
    result = _engine.get_ready_briefing("daily", include_low=True)
    assert [item["headline"] for item in result["stories"]] == ["Airline opens new route to Tokyo"]
    assert result["excluded_count"] == 2
    assert len(day["stories"]) == 3, "the archive itself keeps everything"


def test_the_filter_follows_the_current_lists_and_does_not_rewrite_the_archive(serve, monkeypatch):
    serve(day_with(stored("Boeing stock falls below $200", "capital_markets", 46.5, tier=3)))
    assert _engine.get_ready_briefing("daily")["stories"] == []
    loosened = copy.deepcopy(RELEVANCE)
    loosened["selection"]["exclude_commentary"] = False
    monkeypatch.setattr(story_lifecycle, "load_relevance_config", lambda version=None: loosened)
    assert len(_engine.get_ready_briefing("daily")["stories"]) == 1


def test_trusted_company_results_and_civil_defence_mentions_survive_the_filter(serve):
    serve(day_with(
        stored("Airline reports record quarterly profit", "airline_financials", 70, tier=1),
        stored("Fighter jet escort for airline flight over airspace", "geopolitics_airspace", 60, tier=2),
    ))
    assert len(_engine.get_ready_briefing("daily")["stories"]) == 2


def test_excluded_stories_do_not_count_as_hidden_low(serve):
    serve(day_with(stored("Boeing stock tumbles", "capital_markets", 37, tier=3), stored("Airline adds new route", "route_network_change", 37)))
    result = _engine.get_ready_briefing("daily")
    assert result["hidden_low_count"] == 1 and result["excluded_count"] == 1
