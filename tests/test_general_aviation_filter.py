import pytest

from api import story_lifecycle

SELECTION = story_lifecycle.load_relevance_config()["selection"]
BEA_TITLES = [
    "16/10/2026 General aviation Investigation Opening Accident to the Centrair 101 registered F-CHEZ on 06/10/2026 at Grenoble - Le Versoud AD",
    "16/10/2026 Specialised operations Investigation Opening Accident to the Piper PA18 registered OO-VVA on 12/08/2026 at Saint-Hubert AD (Belgium)",
    "16/10/2026 General aviation Investigation Opening Accident to the flex-wing microlight Ellipse Alize Swissauto Mystic CX identified 77BRD on 05/10/2026 near Thouars AD",
    "16/10/2026 Specialised operations Investigation Opening Serious incident to the Airbus AS350 registered F-GGAO on 02/10/2026 at La Pacaudiere",
]


def story(title, carriers=()):
    return {"headline": title, "entities": {"carriers": [{"entity_id": c} for c in carriers], "groups": []}}


@pytest.mark.parametrize("title", BEA_TITLES + ["Glider pilot killed in Alps crash", "Paraglider collides with cable in Bavaria", "Two dead as ultralight crashes near Lyon"])
def test_general_aviation_accidents_are_out_of_scope(title):
    assert story_lifecycle.is_military_story(story(title), SELECTION)
    assert story_lifecycle.is_excluded(story(title), story_lifecycle.load_relevance_config())


@pytest.mark.parametrize("title", [
    "Airliner and glider collide near Munich airport",             # airline/airport context rescues it
    "Airport closes runway after light aircraft incident, passengers delayed",
    "Lufthansa flight diverted after microlight enters controlled airspace",
])
def test_an_airline_or_airport_context_keeps_the_story(title):
    assert not story_lifecycle.is_military_story(story(title), SELECTION)


def test_a_named_carrier_keeps_the_story():
    assert not story_lifecycle.is_military_story(story("General aviation traffic rules change, says Lufthansa", carriers=["carrier:1"]), SELECTION)


def test_airline_safety_incidents_are_not_affected():
    for title in ("Air India flight diverts to Jaipur after suspected accidental hijack alert", "Ryanair 737 makes emergency landing after engine failure", "Cargo jet crash near Anchorage"):
        assert not story_lifecycle.is_military_story(story(title), SELECTION)
