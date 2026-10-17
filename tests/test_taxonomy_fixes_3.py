import pytest

from api import _engine, entities, market_data, safety_context, story_lifecycle

RELEVANCE = story_lifecycle.load_relevance_config()
SELECTION = RELEVANCE["selection"]
INDEX = entities.EntityIndex.from_csv()
CONFIG = safety_context.load_config()


def kind(title, description=""):
    result = market_data.classify_event_type(title, description)
    return result["event_type"] if result else None


def typed_article(title, description="", **extra):
    article = {"title": title, "description": description, **extra}
    result = market_data.classify_event_type(title, description)
    article["event_type"], article["event_weight"] = (result["event_type"], result["event_weight"]) if result else (None, None)
    entities.annotate_articles([article], INDEX)
    safety_context.enforce([article])
    return article


def story(title):
    return {"headline": title, "entities": {"carriers": [], "groups": []}}


# --- (a) a strike in a military context is a defence item, a strike by staff stays a disruption ------------------------------

@pytest.mark.parametrize("title", [
    "Ukraine says Neptune missile strike hit six Russian Su-34 bombers at air base",
    "Drone strike hits military depot near the border",
    "Russian airstrike destroys fuel storage",
    "Overnight bombardment and air strike reported in Ukraine",
])
def test_a_military_strike_is_a_defence_item_and_not_an_operations_disruption(title):
    assert story_lifecycle.is_military_story(story(title), SELECTION)
    assert story_lifecycle.is_excluded(story(title), RELEVANCE)
    assert kind(title) != "operations_disruption"


@pytest.mark.parametrize("title", [
    "Pilots union announces strike at Air Example next week",
    "Cabin crew walkout: strike disrupts flights across Russia",
    "Labor dispute: ground staff strike, flights cancelled",
])
def test_a_labour_strike_stays_an_operations_disruption(title):
    assert kind(title) == "operations_disruption"
    assert not story_lifecycle.is_military_story(story(title), SELECTION)


def test_a_military_strike_with_an_airport_context_is_not_dropped_but_is_not_a_labour_disruption():
    title = "Drone strike closes airport, passengers stranded"
    assert not story_lifecycle.is_military_story(story(title), SELECTION), "the airport context keeps it in the list"
    assert kind(title) != "operations_disruption"


def test_the_strike_rule_is_defined_once_in_the_defence_exclusion_config():
    rule = SELECTION["military_strike"]
    assert {"missile*", "drone*", "su-34", "ukrain*", "russia*", "military", "air strike", "airstrike*", "bombardment*"} <= set(rule["context"])
    assert {"union*", "pilots", "cabin crew", "labor", "walkout*"} <= set(rule["unless"])
    assert market_data.load_taxonomy_config()["event_types"]["operations_disruption"]["exclude_when_rule"] == "military_strike"


# --- (b) flight numbers: known carrier codes, airline context, never an aircraft model -----------------------------------------

def carrier_codes(text):
    found = INDEX.match({"title": text, "description": ""}) if hasattr(INDEX, "match") else None
    article = {"title": text, "description": ""}
    entities.annotate_articles([article], INDEX)
    return {item["iata"] for item in article["entities"]["carriers"]}


@pytest.mark.parametrize("text", [
    "Serious incident to the Airbus AS350 registered F-GGAO on 02/10/2026",
    "EC135 air ambulance flight lands safely, crew unhurt",
    "The H125 helicopter returned with passengers after a precautionary landing",
])
def test_an_aircraft_model_is_never_a_flight_number(text):
    assert "AS" not in carrier_codes(text) and "EC" not in carrier_codes(text)


def test_a_flight_number_needs_an_airline_context_in_the_text():
    assert "TK" in carrier_codes("Flight TK 1234 to Istanbul diverted after a technical fault")
    assert "TK" not in carrier_codes("Reference TK 1234 filed with the registry")
    assert "AS" in carrier_codes("Passengers on AS 123 from Seattle were rebooked")


def test_the_designator_list_is_data_and_covers_the_helicopters_of_the_reported_case():
    import json
    rules = json.loads((entities.FLIGHT_NUMBER_RULES_PATH).read_text(encoding="utf-8"))
    assert {"AS350", "EC135", "H125", "AW139"} <= set(rules["aircraft_designators"]) and "flights" in rules["context_words"]


def test_the_a350_still_does_not_read_as_aegean():
    assert "A3" not in carrier_codes("Airline passengers will fly the A350 on the route")


# --- (c) safety_incident needs an airline, airport or passenger context ---------------------------------------------------------

GENERAL_AVIATION = [
    "16/10/2026 General aviation Investigation Opening Accident to the Centrair 101 registered F-CHEZ on 06/10/2026 at Grenoble",
    "16/10/2026 Specialised operations Investigation Opening Accident to the Piper PA18 registered OO-VVA on 12/08/2026 at Saint-Hubert AD (Belgium)",
    "16/10/2026 General aviation Investigation Opening Accident to the flex-wing microlight Ellipse Alize identified 77BRD on 05/10/2026 near Thouars AD",
    "16/10/2026 Specialised operations Investigation Opening Serious incident to the Airbus AS350 registered F-GGAO on 02/10/2026 at La Pacaudiere",
    "Pilot survives Louisiana Cessna crash after engine falls off",
    "Nijerya'da özel jetin kapısı havada koptu! Pilotlar üç kez Mayday çağrısı yaptı",
    "Helicopter crash kills two on the coast",
    "Light aircraft crash at a regional airport kills pilot",
    "Beechcraft Bonanza crashes after takeoff, two dead",
]
AIRLINE = [
    "Air India flight diverts to Jaipur after suspected accidental hijack alert",
    "Ryanair 737 makes emergency landing after engine failure",
    "Passenger jet suffers runway excursion in heavy rain",
    "Plane crash near the airport kills ten",
    "Cargo jet crash near Anchorage, freighter lost",
    "Delta flight 1234 returns to Atlanta after bird strike",
]


@pytest.mark.parametrize("title", GENERAL_AVIATION)
def test_general_aviation_and_contextless_accidents_lose_the_safety_type(title):
    article = typed_article(title)
    assert article["event_type"] is None and article["event_weight"] is None, title


@pytest.mark.parametrize("title", AIRLINE)
def test_airline_airport_and_passenger_accidents_keep_the_safety_type(title):
    assert typed_article(title)["event_type"] == "safety_incident", title


def test_a_demoted_story_cannot_reach_critical_or_important_even_from_an_official_tier_one_source():
    levels = RELEVANCE["levels"]
    for title in GENERAL_AVIATION[:4]:
        article = typed_article(title, official=True, reliability_weight=1.0, tier=1)
        score, _ = story_lifecycle.score_article(article, 1, RELEVANCE)
        level = story_lifecycle.level_for(score, levels)
        assert level is None or level["name"] in {"watch", "low"}, (title, score)
    kept = typed_article("Air India flight diverts after hijack alert", official=True, reliability_weight=1.0, tier=1)
    score, _ = story_lifecycle.score_article(kept, 1, RELEVANCE)
    assert story_lifecycle.level_for(score, levels)["name"] in {"critical", "important"}


def test_general_aviation_stays_in_the_list_it_is_no_longer_excluded():
    for title in GENERAL_AVIATION[:3]:
        assert not story_lifecycle.is_military_story(story(title), SELECTION), title
    assert not any(term in SELECTION["exclude_terms"] for term in ("general aviation", "specialised operations", "light aircraft"))


def test_the_pipeline_applies_the_context_rule_after_the_entities_are_annotated(monkeypatch):
    article = {"title": "Pilot survives Louisiana Cessna crash after engine falls off", "description": "", "link": "https://x.example/1", "source": "Trade", "event_type": "safety_incident", "event_weight": 0.95}
    entities.annotate_articles([article], INDEX)
    assert safety_context.enforce([article]) == 1 and article["event_type"] is None
    assert "safety_context.enforce(articles)" in open(_engine.__file__, encoding="utf-8").read()


def test_no_weight_or_threshold_changed():
    types = market_data.load_taxonomy_config()["event_types"]
    assert types["safety_incident"]["weight"] == 0.95 and types["operations_disruption"]["weight"] == 0.8
    assert SELECTION["min_score"] == 40 and SELECTION["archive_min_score"] == 35
    assert [(level["name"], level["min_score"]) for level in RELEVANCE["levels"]] == [("critical", 60), ("important", 45), ("watch", 40), ("low", 35)]


def candidate(title, score, demoted=None):
    url = f"https://example.com/{abs(hash(title))}"
    item = {"story_id": story_lifecycle.stable_story_id(url), "headline": title, "relevance_score": score, "entities": {"carriers": [], "groups": []},
            "original_source": {"url": url, "title": title, "source_name": "Wire", "tier": 2, "official": False}}
    if demoted:
        item["context_demoted_from"] = demoted
    return item


def test_a_demoted_story_stays_in_the_hidden_archive_band_however_low_it_scores():
    stories = [candidate("Cessna crash in Louisiana", 28.5, "safety_incident"), candidate("Unrelated low score item", 28.5), candidate("Airline order", 55)]
    chosen = story_lifecycle.select_stories(stories, SELECTION)
    assert {item["headline"] for item in chosen} == {"Cessna crash in Louisiana", "Airline order"}
    kept = next(item for item in chosen if item["headline"].startswith("Cessna"))
    level = story_lifecycle.level_for(kept["relevance_score"], RELEVANCE["levels"])
    assert level is None, "below every band: archived, never listed"


def test_the_candidate_story_carries_the_demotion_marker():
    article = typed_article("Pilot survives Louisiana Cessna crash after engine falls off", link="https://x.example/c1", source="Trade", published=None)
    article.update({"source_type": "trade_media", "timestamp": 0, "pub_date": ""})
    assert _engine.build_candidate_story(article)["context_demoted_from"] == "safety_incident"
