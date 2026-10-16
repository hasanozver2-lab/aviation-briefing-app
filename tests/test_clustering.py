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


def test_the_same_order_reported_by_five_outlets_is_one_story():
    acg = [
        article("Lessor Aviation Capital Group places record order for 75 Airbus A320neo Family jets", "Aviation24"),
        article("Airbus secures order for 75 Airbus A320neo family aircraft from ACG", "AeroTime", hours=1),
        article("Airbus wins order for 75 A320neo Family jets despite years-long delivery backlog", "AirDataNews", hours=1),
        article("ACG’den Airbus’a 75 uçaklık dev sipariş: Anlaşmanın liste değeri 11,76 milyar dolar", "HavaHaber", hours=3,
                description="Aviation Capital Group, 75 adet Airbus A320neo ailesi uçak sipariş etti."),
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
