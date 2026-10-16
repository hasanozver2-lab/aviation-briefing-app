import json
from datetime import datetime, timedelta, timezone

import pytest

from api import entities, market_data, story_lifecycle

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
BADGES = story_lifecycle.load_badges_config()
V1 = story_lifecycle.load_relevance_config("v1")
V2 = story_lifecycle.load_relevance_config("v2")
INDEX = entities.EntityIndex.from_csv()

THY_CFM_TITLE = "Turkish Airlines signs MOU with CFM for 300 MAX engines and support for over 600"
THY_CFM_TEXT = "Turkish Airlines has signed a Memorandum of Understanding (MOU) with CFM International to provide more than 300 LEAP-1B engines."
DELTA_TITLE = "Delta funding helps Clayton County nonprofit strengthen food delivery services"
DELTA_TEXT = (
    "A Clayton County nonprofit that delivers food directly to Georgia families in need is expanding, with support from Delta. "
    "Delta Air Lines donated a $25,000 grant. About the Community Foundation: it helps turn charitable goals into lasting "
    "impact through tax-smart giving options, personal guidance and local expertise."
)


def article(title, text, reliability, official, tier_source=None):
    classification = market_data.classify_event_type(title, text) or {}
    return {
        "title": title, "description": text, "reliability_weight": reliability, "official": official,
        "event_type": classification.get("event_type"), "event_weight": classification.get("event_weight"),
        "entities": INDEX.find(title, text),
    }


def score(item, publishers, config=V2):
    return story_lifecycle.score_article(item, publishers, config)[0]


# --- versions ------------------------------------------------------------------------------------------

def test_v1_is_kept_unchanged_and_v2_is_the_active_provisional_version():
    raw = json.loads(story_lifecycle.RELEVANCE_CONFIG_PATH.read_text(encoding="utf-8"))
    assert raw["active_version"] == "v2" and raw["versions"]["v2"]["status"] == "provisional"
    assert V1["weights"] == {"event_type": 35, "source_reliability": 20, "entity_prominence": 25, "official_source": 10, "corroboration": 10}
    assert V1["event_type_default"] == 0.2 and V1["version"] == "v1"
    assert story_lifecycle.load_relevance_config()["version"] == "v2"


def test_v2_raises_event_type_and_publisher_count_and_lowers_the_official_bonus():
    assert V2["weights"]["official_source"] < V1["weights"]["official_source"] == 10
    assert V2["weights"]["event_type"] > V1["weights"]["event_type"]
    assert V2["weights"]["corroboration"] > V1["weights"]["corroboration"]
    assert sum(V1["weights"].values()) == sum(V2["weights"].values()) == 100


# --- the diagnosed misclassification -------------------------------------------------------------------------

def test_a_single_boilerplate_hit_in_a_long_description_no_longer_classifies_a_story():
    assert market_data.classify_event_type("Foundation reports on its year", "tax-smart giving options, personal guidance") is None


def test_two_distinct_terms_in_the_description_do_classify():
    result = market_data.classify_event_type("Carrier update", "Quarterly results beat guidance on higher revenue")
    assert result["event_type"] == "airline_financials"


def test_the_delta_community_announcement_is_a_csr_story_not_a_financial_one():
    assert market_data.classify_event_type(DELTA_TITLE, DELTA_TEXT)["event_type"] == "community_csr"


def test_the_thy_cfm_engine_agreement_is_a_fleet_deal():
    assert market_data.classify_event_type(THY_CFM_TITLE, THY_CFM_TEXT)["event_type"] == "fleet_orders"
    assert market_data.classify_event_type("THY ve CFM'den 600 motorluk dev anlaşma", "")["event_type"] == "fleet_orders"


@pytest.mark.parametrize("title, expected", [
    ("Pilots strike halts flights at Air Example", "operations_disruption"),
    ("Plane crash near regional airport, rescue under way", "safety_incident"),
    ("Airliner makes emergency landing after engine failure", "safety_incident"),
    ("Airline donates to a local scholarship fund", "community_csr"),
])
def test_new_event_types_classify(title, expected):
    assert market_data.classify_event_type(title)["event_type"] == expected


# --- regression: a critical story always outscores an irrelevant community announcement -----------------------

def test_thy_cfm_always_scores_above_the_community_announcement_even_in_the_worst_case():
    thy_worst = article(THY_CFM_TITLE, THY_CFM_TEXT, reliability=0.4, official=False)      # one trade outlet, nothing else
    for publishers in (1, 2, 3, 6):                                                          # Delta at its best: official, tier 1, covered widely
        delta_best = article(DELTA_TITLE, DELTA_TEXT, reliability=1.0, official=True)
        assert score(thy_worst, 1) > score(delta_best, publishers), publishers


@pytest.mark.parametrize("title", [
    "United donates $50,000 to a children's scholarship program",
    "Lufthansa volunteers help at a local food bank",
    "American Airlines charity auction raises funds for nonprofit",
])
def test_other_community_announcements_stay_below_the_critical_story(title):
    thy = article(THY_CFM_TITLE, THY_CFM_TEXT, reliability=0.4, official=False)
    other = article(title, "", reliability=1.0, official=True)
    assert score(thy, 1) > score(other, 3)


def test_v1_failed_this_regression_which_is_why_v2_exists():
    thy = article(THY_CFM_TITLE, THY_CFM_TEXT, reliability=0.4, official=False)
    delta = article(DELTA_TITLE, DELTA_TEXT, reliability=1.0, official=True)
    delta_as_v1_saw_it = {**delta, "event_type": "airline_financials", "event_weight": 0.85}
    assert score(delta_as_v1_saw_it, 1, V1) > score({**thy, "event_weight": None}, 1, V1)


# --- breaking needs an allowed event type --------------------------------------------------------------------------------

def stored(event_type, score_value=95.0, reliability=1.0):
    return {"story_id": "s", "event_type": event_type, "relevance_score": score_value, "score_components": {"source_reliability": reliability},
            "first_seen_at": story_lifecycle.to_iso(NOW), "last_updated_at": story_lifecycle.to_iso(NOW),
            "published_at_iso": story_lifecycle.to_iso(NOW - timedelta(hours=1))}


def test_the_allowed_breaking_event_types_are_the_agreed_ones_and_all_exist():
    allowed = set(BADGES["breaking"]["allowed_event_types"])
    assert allowed == {"geopolitics_airspace", "safety_incident", "fuel_energy", "airline_financials", "operations_disruption"}
    assert allowed <= set(market_data.load_taxonomy_config()["event_types"])


@pytest.mark.parametrize("event_type", sorted({"geopolitics_airspace", "safety_incident", "fuel_energy", "airline_financials", "operations_disruption"}))
def test_allowed_event_types_can_be_breaking(event_type):
    assert "breaking" in story_lifecycle.compute_badges(stored(event_type), NOW, BADGES)


@pytest.mark.parametrize("event_type", [None, "community_csr", "fleet_orders", "capital_markets", "fx_currency", "macro_demand"])
def test_other_stories_are_never_breaking_whatever_their_score(event_type):
    assert "breaking" not in story_lifecycle.compute_badges(stored(event_type, 100.0), NOW, BADGES)


def test_an_allowed_type_below_the_critical_score_is_not_breaking():
    assert "breaking" not in story_lifecycle.compute_badges(stored("safety_incident", BADGES["breaking"]["critical_score"] - 1), NOW, BADGES)


# --- selection ----------------------------------------------------------------------------------------------------------------

def test_selection_keeps_stories_at_or_above_the_threshold_best_first_up_to_the_cap():
    stories = [{"story_id": f"s{index}", "relevance_score": value} for index, value in enumerate([30, 45, 80, 60, 44.9, 45])]
    chosen = story_lifecycle.select_stories(stories, {"min_score": 45, "max_per_run": 3})
    assert [item["relevance_score"] for item in chosen] == [80, 60, 45]


def test_the_active_selection_threshold_keeps_the_critical_story_and_drops_the_community_one():
    thy = article(THY_CFM_TITLE, THY_CFM_TEXT, reliability=0.4, official=False)
    delta = article(DELTA_TITLE, DELTA_TEXT, reliability=1.0, official=True)
    minimum = V2["selection"]["min_score"]
    assert score(thy, 1) >= minimum
    assert score(delta, 1) < minimum


def test_cluster_representative_is_the_most_reliable_source_then_the_earliest():
    articles = [
        {"title": "Airbus A220 order announced", "link": "https://a.example/1", "reliability_weight": 0.4, "timestamp": 100},
        {"title": "Airbus A220 order announced today", "link": "https://b.example/1", "reliability_weight": 1.0, "timestamp": 300},
        {"title": "Airbus A220 order announced today again", "link": "https://c.example/1", "reliability_weight": 1.0, "timestamp": 200},
        {"title": "Qantas opens a new Perth route", "link": "https://d.example/1", "reliability_weight": 0.4, "timestamp": 100},
    ]
    chosen = story_lifecycle.cluster_representatives(articles)
    assert sorted(item["link"] for item in chosen) == ["https://c.example/1", "https://d.example/1"]


def test_company_results_are_breaking_only_from_a_reliable_source():
    assert "breaking" in story_lifecycle.compute_badges(stored("airline_financials", reliability=1.0), NOW, BADGES)
    assert "breaking" in story_lifecycle.compute_badges(stored("airline_financials", reliability=0.8), NOW, BADGES)
    # stock commentary on a finance site (reliability 0.7) is not breaking news
    assert "breaking" not in story_lifecycle.compute_badges(stored("airline_financials", reliability=0.7), NOW, BADGES)


def test_the_source_requirement_applies_only_to_the_configured_types():
    assert "breaking" in story_lifecycle.compute_badges(stored("safety_incident", reliability=0.4), NOW, BADGES)


# --- military and defence items are out of scope ------------------------------------------------------------------------

SELECTION = V2["selection"]


def military(headline, carriers=()):
    return {"headline": headline, "relevance_score": 99.0, "story_id": headline, "entities": {"carriers": [{"slug": c} for c in carriers], "groups": []}}


@pytest.mark.parametrize("headline", [
    "Australia's $1.7B air battle system links RAAF F-35As to missile defense network",
    "Ukraine claims six Russian Su-34 bombers damaged in Neptune missile strike",
    "MSB'den F-35 ve C-130J açıklaması: 6 savaş uçağı için temaslar sürüyor",
    "Belçika, bu yıl Ukrayna'ya 10 'F-16' savaş uçağı teslim edecek",
])
def test_military_stories_without_an_airline_are_not_selected(headline):
    assert story_lifecycle.select_stories([military(headline)], SELECTION) == []


@pytest.mark.parametrize("headline, carriers", [
    ("Qantas to carry F-35 parts on its freighters", ["qantas"]),                       # an airline is involved
    ("Missile strike closes airspace over the region; carriers reroute", []),            # civil aviation context
    ("Airport shut after drone alert near an air force base", []),
    ("Pilot survives Louisiana Cessna crash after engine falls off", []),                # not military at all
])
def test_civil_aviation_stories_are_kept_even_when_military_words_appear(headline, carriers):
    assert len(story_lifecycle.select_stories([military(headline, carriers)], SELECTION)) == 1


def test_v1_does_not_exclude_anything():
    assert len(story_lifecycle.select_stories([military("RAAF F-35A bombers")], V1["selection"])) == 1


# --- route_network_change -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("title", [
    "New Lufthansa Airbus A350-1000 to fly first to Tokyo",
    "Lufthansa selects Tokyo as first destination for Airbus A350-1000",
    "Lufthansa picks Tokyo for December launch of first Airbus A350-1000",
    "ITA Airways to resume Rome-Caracas flights after 12-year absence",
    "Air Canada Launches Nonstop Flights To New US City",
    "Qatar Airways adds flights to Manila and deploys A350 on the route",
    "Emirates and Delta announce a new codeshare agreement",
    "Airline will suspend its Frankfurt service for the winter",
])
def test_route_and_network_changes_are_classified(title):
    assert market_data.classify_event_type(title)["event_type"] == "route_network_change"


@pytest.mark.parametrize("title", [
    "Emirates brings global travel rehearsal programme to Colombia",     # an accessibility programme, not a route
    "Emirates turns to Manila for first pilot recruitment drive in the Philippines",   # hiring
    "Lufthansa tells jets to carry extra fuel as Frankfurt, Zurich face supply crunch",
])
def test_news_that_is_not_a_route_change_is_not_classified_as_one(title):
    result = market_data.classify_event_type(title)
    assert result is None or result["event_type"] != "route_network_change"


def test_route_changes_weigh_as_much_as_fleet_orders():
    types = market_data.load_taxonomy_config()["event_types"]
    assert types["route_network_change"]["weight"] == types["fleet_orders"]["weight"] == 0.7


def test_the_lufthansa_tokyo_launch_from_the_official_newsroom_outscores_a_community_announcement():
    tokyo = article("New Lufthansa Airbus A350-1000 to fly first to Tokyo", "Ferry flight to Munich. First scheduled flight on December 3 from Munich to Tokyo/Haneda.", reliability=1.0, official=True)
    community = article(DELTA_TITLE, DELTA_TEXT, reliability=1.0, official=True)
    assert tokyo["event_type"] == "route_network_change"
    assert score(tokyo, 1) > score(community, 3)


# --- finance commentary -----------------------------------------------------------------------------------------------------------

COMMENTARY = V2["commentary"]


def finance_story(title, tier, official=False, event_type=None, score_value=60.0):
    return {"story_id": title, "headline": title, "event_type": event_type, "relevance_score": score_value,
            "original_source": {"tier": tier, "official": official}, "entities": {}}


@pytest.mark.parametrize("title", [
    "Boeing Fell Back Below $200 Ahead of a Strike Deadline. Here's Why I'd Buy the Fear",
    "Boeing Price Target Slashed To $235 By RBC",
    "Is American Airlines Stock's Drop A Chance To Buy?",
    "Morgan Stanley flags Delta Air Lines shift Wall Street misses, sees 64% upside",
    "Boeing (BA) Outperforms Broader Market: What You Need to Know",
    "Should you buy Delta shares now?",
])
def test_stock_commentary_titles_from_an_untrusted_source_are_commentary(title):
    assert story_lifecycle.is_finance_commentary(finance_story(title, tier=3), COMMENTARY)


@pytest.mark.parametrize("title", [
    "Boeing Price Target Slashed To $235 By RBC",
    "Delta shares fall after the company cuts its outlook",
])
def test_the_same_headline_from_an_official_or_tier_two_source_is_kept(title):
    assert not story_lifecycle.is_finance_commentary(finance_story(title, tier=1, official=True), COMMENTARY)
    assert not story_lifecycle.is_finance_commentary(finance_story(title, tier=2), COMMENTARY)


def test_financial_news_without_a_stock_pattern_is_kept_only_from_official_or_tier_two_sources():
    results = finance_story("Quarterly results beat expectations", tier=3, event_type="airline_financials")
    assert story_lifecycle.is_finance_commentary(results, COMMENTARY)
    assert not story_lifecycle.is_finance_commentary(dict(results, original_source={"tier": 3, "official": True}), COMMENTARY)
    assert not story_lifecycle.is_finance_commentary(dict(results, original_source={"tier": 2, "official": False}), COMMENTARY)


def test_non_financial_stories_from_any_source_are_never_commentary():
    assert not story_lifecycle.is_finance_commentary(finance_story("Airbus A220 order announced", tier=4, event_type="fleet_orders"), COMMENTARY)


def test_commentary_is_scored_down_and_kept_out_of_the_list():
    item = article("Is American Airlines Stock's Drop A Chance To Buy?", "American Airlines stock earnings revenue", reliability=0.7, official=False)
    item.update(tier=3, event_type="airline_financials", event_weight=0.85)
    plain = score(item, 1, {**V2, "commentary": None})
    penalised = score(item, 1)
    assert penalised == round(plain * COMMENTARY["score_multiplier"], 1) and penalised < plain

    commentary_story = finance_story(item["title"], tier=3, event_type="airline_financials", score_value=90.0)
    assert story_lifecycle.select_stories([commentary_story], SELECTION, COMMENTARY) == []
    assert len(story_lifecycle.select_stories([dict(commentary_story, original_source={"tier": 1, "official": True})], SELECTION, COMMENTARY)) == 1


def test_v1_has_no_commentary_filter():
    assert "commentary" not in V1
