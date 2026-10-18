import json
from datetime import datetime, timedelta, timezone

import pytest

from api import _engine, benchmark_search, market_data

NOW = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(hours=48)


def gemini_response(items, grounded_uris=None):
    chunks = [{"web": {"uri": uri}} for uri in (grounded_uris or [])]
    return {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "```json\n" + json.dumps({"items": items}) + "\n```"}]
                },
                "groundingMetadata": {"groundingChunks": chunks},
            }
        ]
    }


def test_prompt_covers_all_mandatory_benchmark_and_wire_sources():
    prompt = benchmark_search.build_search_prompt(NOW, CUTOFF)
    for required in (
        "ideaworkscompany.com",
        "oag.com",
        "cirium.com",
        "ch-aviation.com",
        "iata.org",
        "aci.aero",
        "centreforaviation.com",
        "eurocontrol.int",
        "reuters.com",
        "bloomberg.com",
        "ft.com",
        "wsj.com",
        "aviationweek.com",
        "A321XLR",
        "CASK/RASK",
        "LHR, CDG, AMS, FRA",
    ):
        assert required in prompt


def test_collect_parses_grounded_benchmark_and_wire_items_and_filters_off_topic():
    raw_items = [
        {
            "title": "IdeaWorksCompany reports global airline ancillary revenue reaches $148 billion",
            "url": "https://ideaworkscompany.com/reports/2026-ancillary-revenue-yearbook",
            "source_name": "IdeaWorksCompany",
            "published_at": "2026-10-17",
            "description": "Global ancillary revenue rose 11% driven by unbundling and FFP co-brand credit cards.",
        },
        {
            "title": "OAG Megahubs 2026 index ranks top connecting banks and OTP performance",
            "url": "https://www.oag.com/blog/megahubs-index-2026",
            "source_name": "OAG",
            "published_at": "2026-10-18",
            "description": "IST and LHR lead international connectivity as MCT windows tighten.",
        },
        {
            "title": "United Airlines warns rising jet fuel costs could hit Q2 earnings",
            "url": "https://www.reuters.com/business/aerospace-defense/united-airlines-warns-fuel-costs-2026-10-17/",
            "source_name": "Reuters",
            "published_at": "2026-10-17",
            "description": "United Airlines said higher jet fuel prices could reduce quarterly profit.",
        },
        {
            "title": "SpaceX valuation hits $1.75 trillion ahead of IPO",
            "url": "https://www.reuters.com/technology/space/spacex-valuation-2026-10-17/",
            "source_name": "Reuters",
            "published_at": "2026-10-17",
            "description": "Off-topic space item that should be filtered out.",
        },
        {
            "title": "Outdated Cirium report from last month",
            "url": "https://www.cirium.com/thoughtcloud/old-report",
            "source_name": "Cirium",
            "published_at": "2026-09-01",
            "description": "Stale item outside the 48h window.",
        },
    ]
    articles, report = benchmark_search.collect(
        "fake-api-key",
        NOW,
        CUTOFF,
        post=lambda: gemini_response(raw_items),
        classify_topics_fn=_engine.classify_topics,
    )
    assert report == {"status": "active", "error": "", "articles": 3}
    by_source = {a["source"]: a for a in articles}
    assert set(by_source) == {"IdeaWorksCompany", "OAG", "Reuters"}
    assert by_source["IdeaWorksCompany"]["tier"] == 2
    assert by_source["IdeaWorksCompany"]["reliability_weight"] == 0.9
    assert by_source["IdeaWorksCompany"]["via_benchmark_search"] is True
    assert by_source["Reuters"]["source_type"] == "mainstream"
    assert by_source["Reuters"]["tier"] == 2
    assert by_source["Reuters"]["basis"] == "headline_only"
    assert "finance_investor" in by_source["IdeaWorksCompany"]["topics"]
    assert "route_network" in by_source["OAG"]["topics"]


def test_collect_without_api_key_returns_not_configured_without_raising():
    articles, report = benchmark_search.collect("", NOW, CUTOFF, include_rss=False)
    assert articles == [] and report["status"] == "not_configured"


def test_collect_handles_network_failure_gracefully():
    def failing_post():
        raise TimeoutError("Gemini search timed out")

    articles, report = benchmark_search.collect("fake-api-key", NOW, CUTOFF, post=failing_post)
    assert articles == [] and report == {"status": "error", "error": "TimeoutError", "articles": 0}


@pytest.mark.parametrize("title, expected_type", [
    ("IdeaWorksCompany: Global airline ancillary revenue and unbundling trends surge", "airline_financials"),
    ("Airline reduces unit cost CASK by 8% with new A321XLR deployment", "airline_financials"),
    ("OAG Megahubs index highlights hub-bypass and minimum connection time shifts", "route_network_change"),
    ("Pratt & Whitney GTF inspections push AOG count higher across European fleets", "operations_disruption"),
    ("Eurocontrol reports European ATC delays and OTP pressure across core hubs", "operations_disruption"),
    ("Carrier signs ACMI wet-lease agreement to cover summer A321XLR capacity", "fleet_orders"),
    ("IATA and ACI World report global RPK and air cargo CTK demand growth", "macro_demand"),
    ("Boeing Commercial Market Outlook 2026 - 2045 projects 44,000 new airplanes", "macro_demand"),
    ("EUROCONTROL Forecast Update 2026-2032 - Spring projects 11.3 million flights", "macro_demand"),
])
def test_benchmark_and_fleet_economics_terms_classify_into_event_types(title, expected_type):
    classified = market_data.classify_event_type(title, "")
    assert classified is not None and classified["event_type"] == expected_type


def test_blocked_official_airlines_and_oems_resolve_as_tier1_official_publishers():
    thy = benchmark_search.resolve_publisher_meta("https://press.turkishairlines.com/en/news/2026", "Turkish Airlines")
    rtx = benchmark_search.resolve_publisher_meta("https://www.rtx.com/news/2026/gtf-update", "RTX")
    prn = benchmark_search.resolve_publisher_meta("https://www.prnewswire.com/news-releases/airline-301.html", "PR Newswire")
    assert thy["official"] is True and thy["tier"] == 1 and thy["airline_code"] == "TK"
    assert rtx["official"] is True and rtx["tier"] == 1 and rtx["reliability_weight"] == 0.95
    assert prn["source_type"] == "trade_media" and prn["tier"] == 2


def test_extract_publication_page_parses_boeing_cmo_and_eurocontrol_forecast():
    boeing_html = """
    <html><head><title>Commercial Market Outlook</title></head><body>
    <h1>Commercial Market Outlook</h1>
    <h4>Commercial Market Outlook 2026 - 2045</h4>
    <ul>
      <li>The global commercial airplanes fleet is expected to grow nearly 80% to more than 50,000 airplanes by 2045.</li>
      <li>Globally, operators are forecasted to need nearly 44,000 new airplanes over the next 20 years.</li>
    </ul>
    </body></html>
    """
    title, desc = benchmark_search.extract_publication_page(
        boeing_html,
        fallback_title="Boeing Commercial Market Outlook",
        brand_prefix="Boeing",
    )
    assert "Boeing Commercial Market Outlook 2026 - 2045" == title
    assert "50,000 airplanes" in desc and "44,000 new airplanes" in desc

    eurocontrol_html = """
    <html><head>
      <meta property="og:title" content="EUROCONTROL Forecast Update 2026-2032 - Spring" />
      <meta property="og:description" content="This Seven-Year Forecast (Spring 2026) builds on our October 2025 forecast and incorporates the latest observed flight trends." />
    </head><body>
      <p>Traffic in the ECAC area is now expected to reach around 11.3 million flights for the year, corresponding to +2.7% growth compared with 2025.</p>
    </body></html>
    """
    ec_title, ec_desc = benchmark_search.extract_publication_page(
        eurocontrol_html,
        fallback_title="EUROCONTROL Forecast Update",
        brand_prefix="Eurocontrol",
    )
    assert ec_title == "EUROCONTROL Forecast Update 2026-2032 - Spring"
    assert "11.3 million flights" in ec_desc and "+2.7%" in ec_desc


def test_apply_search_enrichment_populates_thin_rss_descriptions_and_corroborating_sources():
    seeds = [
        {
            "title": "Southwest, United Shake Up Their Frequent-Flier Programs",
            "source": "The Wall Street Journal",
            "description": "",
            "basis": "headline_only",
            "topics": [],
        }
    ]
    response = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": json.dumps({
                                "enrichments": [
                                    {
                                        "index": 0,
                                        "description": "Southwest and United revised loyalty tier thresholds by 15% and expanded co-brand card earning rates for 2027.",
                                        "corroborating_sources": ["The Wall Street Journal", "Reuters"],
                                    }
                                ],
                                "items": [],
                            })
                        }
                    ]
                }
            }
        ]
    }
    count = benchmark_search.apply_search_enrichment(response, seeds, classify_topics_fn=_engine.classify_topics)
    assert count == 1
    assert "15%" in seeds[0]["description"]
    assert seeds[0]["corroborating_sources"] == ["The Wall Street Journal", "Reuters"]
    assert "finance_investor" in seeds[0]["topics"]


def test_strategic_reports_are_classified_and_separated_from_daily_breaking_news():
    from api import story_lifecycle

    boeing_cmo = {
        "title": "Boeing Commercial Market Outlook 2026 - 2045",
        "link": "https://www.boeing.com/commercial/market/commercial-market-outlook",
        "source": "Boeing",
    }
    eurocontrol = {
        "title": "EUROCONTROL Forecast Update 2026-2032 - Spring",
        "link": "https://www.eurocontrol.int/publication/eurocontrol-forecast-2026-2032",
        "source": "Eurocontrol",
    }
    iata_new_report = {
        "title": "IATA Global Outlook for Air Transport 2026 Report",
        "link": "https://www.iata.org/en/publications/global-outlook-2026",
        "source": "IATA",
    }
    breaking_news = {
        "title": "United Airlines warns rising jet fuel costs could hit Q2 earnings",
        "link": "https://www.reuters.com/business/aerospace-defense/united-airlines-warns-fuel-costs-2026-10-17/",
        "source": "Reuters",
    }
    assert story_lifecycle.is_strategic_report(boeing_cmo) is True
    assert story_lifecycle.is_strategic_report(eurocontrol) is True
    assert story_lifecycle.is_strategic_report(iata_new_report) is True
    assert story_lifecycle.is_strategic_report(breaking_news) is False

    # Strategic reports have their own bucket in select_stories and do not crowd out daily breaking news
    daily_candidates = [
        {"story_id": f"daily-{i}", "headline": f"Airline route update {i}", "relevance_score": 60 - i, "is_strategic_report": False}
        for i in range(3)
    ]
    report_candidates = [
        {"story_id": f"report-{i}", "headline": f"Boeing Commercial Market Outlook {i}", "relevance_score": 85 - i, "is_strategic_report": True}
        for i in range(3)
    ]
    selected = story_lifecycle.select_stories(
        daily_candidates + report_candidates,
        {"min_score": 40, "max_per_run": 2, "max_strategic_per_run": 2},
    )
    selected_ids = {s["story_id"] for s in selected}
    assert selected_ids == {"daily-0", "daily-1", "report-0", "report-1"}

