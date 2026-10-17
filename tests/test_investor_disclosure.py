import pytest

from api import market_data

TYPES = market_data.load_taxonomy_config()["event_types"]


def kind(title, description=""):
    result = market_data.classify_event_type(title, description)
    return result["event_type"] if result else None


@pytest.mark.parametrize("title", [
    "JetBlue prices $500 million senior notes offering",
    "Copa Holdings announces debt offering",
    "Alaska Air Group announces proposed convertible notes offering",
    "Spirit AeroSystems amends credit facility",
    "United Airlines closes new revolving credit facility",
    "Delta Air Lines announces notes offering",
])
def test_debt_and_financing_announcements_are_investor_disclosures(title):
    result = market_data.classify_event_type(title, "")
    assert result == {"event_type": "investor_disclosure", "event_weight": 0.45}


@pytest.mark.parametrize("title, expected", [
    ("Delta Air Lines Reports September Quarter 2026 Financial Results", "airline_financials"),
    ("United Airlines raises full-year earnings guidance", "airline_financials"),
    ("Alaska Air Group declares quarterly dividend", "airline_financials"),
    ("Boeing announces $2 billion share repurchase program", "capital_markets"),
    ("Airline stock falls after analyst rating cut", "capital_markets"),
    ("Embraer announces order for 20 E195-E2 jets", "fleet_orders"),
])
def test_the_other_investor_announcements_keep_their_types(title, expected):
    assert kind(title) == expected


def test_only_the_new_type_was_added_and_no_weight_changed():
    assert TYPES["investor_disclosure"]["weight"] == TYPES["capital_markets"]["weight"] == 0.45
    assert TYPES["airline_financials"]["weight"] == 0.85 and TYPES["safety_incident"]["weight"] == 0.95 and TYPES["operations_disruption"]["weight"] == 0.8
    assert TYPES["fleet_orders"]["weight"] == 0.7
