import pytest

from api import clustering, entities, market_data, story_lifecycle

INDEX = entities.EntityIndex.from_csv()
CONFIG = clustering.load_clustering_config()
HOUR = 3600
BASE_TIME = 1_760_000_000


def article(title, source="Wire", hours=0, reliability=0.4, description=""):
    result = market_data.classify_event_type(title, description) or {}
    return {
        "title": title, "description": description, "source": source, "link": f"https://{source.lower().replace(' ', '')}.example/{abs(hash(title))}",
        "timestamp": BASE_TIME + hours * HOUR, "reliability_weight": reliability, "official": False,
        "event_type": result.get("event_type"), "event_weight": result.get("event_weight"), "entities": INDEX.find(title, description),
    }


def groups(articles):
    return [[articles[i]["title"] for i in indexes] for indexes in clustering.cluster_articles(articles, CONFIG) if len(indexes) > 1]


THY_CFM = [
    article("Turkish Airlines signs MOU with CFM for 300 MAX engines and support for over 600", "AeroTime"),
    article("Turkish Airlines and CFM sign MOU for more than 600 LEAP-1B engines", "Yahoo Finance", hours=1),
    article("THY ve CFM’den 600 motorluk dev anlaşma.. Murat Şeker’den ilk değerlendirme", "HavaHaber", hours=2),
    article("THY ve CFM’den dev anlaşma: 600’den fazla LEAP-1B motoru için imzalar atıldı", "HavaHaber 2", hours=2),
]


def test_english_and_turkish_reports_of_one_event_become_one_story():
    clusters = clustering.cluster_articles(THY_CFM, CONFIG)
    assert clusters == [[0, 1, 2, 3]]


def test_the_same_order_reported_by_four_outlets_is_one_story():
    """Real titles and descriptions of the Aviation Capital Group order, English and Turkish."""
    acg = [
        article("Lessor Aviation Capital Group places record order for 75 Airbus A320neo Family jets", "Aviation24",
                description="Aviation Capital Group (ACG) has signed a firm order for 75 Airbus A320neo Family aircraft, the largest order in the California-based lessor's nearly 40-year history. The deal brings its cumulative orders for the aircraft family to 190."),
        article("Airbus secures order for 75 Airbus A320neo family aircraft from ACG", "AeroTime", hours=1,
                description="Airbus has secured an order for 75 Airbus A320neo family jets from Aviation Capital Group (ACG)"),
        article("Aviation Capital Group Grows Portfolio with Order for 75 Airbus A320neo Family Aircraft, the Largest Order", "Yahoo Finance", hours=1,
                description='Aviation Capital Group LLC ("ACG") today announced that it has finalized a new order with Airbus for 75 A320neo Family aircraft.'),
        article("ACG’den Airbus’a 75 uçaklık dev sipariş: Anlaşmanın liste değeri 11,76 milyar dolar", "HavaHaber", hours=3,
                description="ABD merkezli uçak kiralama şirketi Aviation Capital Group (ACG), Airbus’a 75 adet A320neo siparişi verdi. Anlaşmanın liste fiyatları üzerinden toplam değeri 11,76 milyar dolara ulaşıyor."),
    ]
    assert len(groups(acg)) == 1 and len(groups(acg)[0]) == 4


def test_two_different_stories_about_the_same_airline_stay_separate():
    stories = [
        article("Lufthansa tells jets to carry extra fuel as Frankfurt, Zurich face supply crunch", "AeroTime"),
        article("Lufthansa selects Tokyo as first destination for Airbus A350-1000", "AirDataNews", hours=1),
        article("Lufthansa says goodbye to the A340-600", "Flightradar24", hours=2),
    ]
    assert groups(stories) == []


def test_a_podcast_cannot_chain_unrelated_stories_together():
    stories = [
        article("Lufthansa tells jets to carry extra fuel as Frankfurt, Zurich face supply crunch", "AeroTime"),
        article("Southwest replaces A-List with new loyalty tiers, adds international rewards", "AeroTime", hours=1),
        article("Simple Flying Podcast Episode 307: Southwest Airlines' New Loyalty Program, Lufthansa Adds Extra Fuel", "Simple Flying", hours=2),
    ]
    assert groups(stories) == []


def test_articles_far_apart_in_time_are_not_the_same_story():
    stories = [THY_CFM[0], {**THY_CFM[1], "timestamp": BASE_TIME + (CONFIG["window_hours"] + 1) * HOUR}]
    assert groups(stories) == []


def test_near_identical_titles_join_without_any_entity():
    stories = [article("Regional carrier opens a new base in the north", "A"), article("Regional carrier opens a new base in the north today", "B", hours=1)]
    assert len(groups(stories)) == 1


def test_sharing_only_an_entity_name_is_not_enough():
    stories = [article("Delta orders 20 Airbus A350 jets for long haul", "A"), article("Delta opens a new lounge in Atlanta", "B", hours=1)]
    assert groups(stories) == []


def test_entity_matching_needs_a_shared_entity():
    stories = [article("Fuel supplier agrees 600 million contract with ministry", "A"),
               article("Software vendor wins 600 million contract after tender", "B", hours=1)]
    assert all(not item["entities"]["carriers"] for item in stories)
    assert groups(stories) == []                     # three shared words, but no shared airline/airport/aircraft


# --- what clustering does for scoring and for the archive -------------------------------------------------

def test_corroboration_finally_counts_for_a_widely_reported_story():
    stories = [{"headline": THY_CFM[0]["title"], "original_source": {"url": THY_CFM[0]["link"], "title": THY_CFM[0]["title"], "source_name": "AeroTime"}}]
    lonely = story_lifecycle.enrich_stories([dict(stories[0], original_source=dict(stories[0]["original_source"]))], THY_CFM[:1])[0]
    joined = story_lifecycle.enrich_stories(stories, THY_CFM)[0]
    assert lonely["source_count"] == 1 and joined["source_count"] == 4
    assert joined["relevance_score"] > lonely["relevance_score"]
    assert [entry["name"] for entry in joined["sources"]] == ["AeroTime", "Yahoo Finance", "HavaHaber", "HavaHaber 2"]


def test_one_representative_story_per_cluster_the_most_reliable_source():
    stories = [dict(THY_CFM[0], reliability_weight=0.4), dict(THY_CFM[1], reliability_weight=0.8), dict(THY_CFM[2], reliability_weight=0.4)]
    chosen = story_lifecycle.cluster_representatives(stories)
    assert len(chosen) == 1 and chosen[0]["source"] == "Yahoo Finance"


@pytest.mark.parametrize("term", ["podcast", "episode", "weekly", "roundup"])
def test_roundup_terms_are_configured(term):
    assert term in CONFIG["roundup_terms"]


# --- the rules for stories without a shared carrier -------------------------------------------------------------

def test_a_story_with_only_a_broad_aircraft_family_joins_through_shared_signals():
    """'300+ Engines: Major Airline ... 737 MAX' names no airline; numbers, the engine maker and the engine model link it."""
    lonely = article("300+ Engines: Major Airline Signs Huge Deal To Power Its Boeing 737 MAX Fleet", "Simple Flying", hours=3,
                     description="A deal with CFM International includes 100s of LEAP-1B engines and the ability to establish an MRO infrastructure in Turkey.")
    thy = article("Turkish Airlines and CFM sign MOU for more than 600 LEAP-1B engines", "Yahoo Finance", hours=1,
                  description="Turkish Airlines signed an MOU with CFM International for more than 600 LEAP-1B engines, including 300 for the 737 MAX.")
    assert not (clustering.entity_ids(lonely, CONFIG) & clustering.entity_ids(thy, CONFIG)), "the only shared entity is a broad family"
    assert len(groups([thy, lonely])) == 1


def test_a_broad_entity_or_a_single_number_alone_never_merges_two_stories():
    boeing_a = article("Boeing delivers 50 jets in the quarter", "A", description="Boeing says deliveries rose.")
    boeing_b = article("Boeing faces a strike deadline at its factories", "B", hours=1, description="Union members vote on the 737 MAX line contract.")
    assert groups([boeing_a, boeing_b]) == []
    only_numbers = [article("Carrier announces 300 new hires and 75 trainee pilots", "A"), article("Lessor takes 300 aircraft and 75 engines into its portfolio", "B", hours=1)]
    assert groups(only_numbers) == []


def test_digits_inside_a_model_designator_are_not_a_second_number():
    left = article("US Navy receives first C-130J for conversion into E-130J command aircraft", "A", description="The C-130J conversion programme.")
    right = article("England, Greece and Turkey: a strange C-130J story", "B", hours=1, description="C-130B and C-130J transports change hands.")
    assert groups([left, right]) == []


def test_numeric_html_entities_are_not_signals():
    noisy = article("Japan&#8217;s carrier opens a route", "A", description="The route&#8230; starts soon&#8230; Japan&#8217;s capital")
    assert not {item for item in clustering.signals(noisy, CONFIG) if item.isdigit()}


def test_a_shared_carrier_and_a_shared_aircraft_variant_make_one_story_but_the_carrier_alone_does_not():
    base = "Lufthansa schedules first A350-1000 passenger flight to Tokyo"
    variants = [article(base, "A"), article("Lufthansa selects Tokyo as first destination for Airbus A350-1000", "B", hours=1),
                article("New Lufthansa Airbus A350-1000 to fly first to Tokyo", "C", hours=2)]
    assert len(groups(variants)) == 1 and len(groups(variants)[0]) == 3
    other = [article("Lufthansa says goodbye to the A340-600", "A"), article("Lufthansa could transfer eight Airbus A350 jets to TAP after 2030", "B", hours=1)]
    assert groups(other) == []


def test_signals_need_compatible_event_types():
    a = article("Carrier signs MOU for 600 LEAP-1B engines with CFM", "A")
    b = article("Strike hits CFM production of 600 LEAP-1B engines", "B", hours=1)
    a["event_type"], b["event_type"] = "fleet_orders", "operations_disruption"
    assert groups([a, b]) == []
    b["event_type"] = None
    assert len(groups([a, b])) == 1
