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


def test_collect_uses_publisher_articles_without_calling_search(monkeypatch):
    published = NOW - timedelta(days=1)
    article = benchmark_search._build_article(
        "Boeing Commercial Market Outlook", "https://www.boeing.com/commercial/market/commercial-market-outlook",
        "Publisher forecasts 44000 deliveries.", benchmark_search.BENCHMARK_PUBLISHERS["boeing.com"],
        published, NOW,
    )
    monkeypatch.setattr(benchmark_search, "collect_strategic_publications", lambda *args, **kwargs: [article])
    monkeypatch.setattr(benchmark_search, "collect_google_news_rss", lambda *args, **kwargs: [])
    def forbidden_search():
        pytest.fail("Collection must not call Gemini for source data")
    articles, report = benchmark_search.collect("", NOW, CUTOFF, post=forbidden_search)
    assert articles == [article]
    assert articles[0]["timestamp"] == published.timestamp()
    assert report == {"status": "active", "error": "", "articles": 1}


def test_collect_without_api_key_returns_not_configured_without_raising():
    articles, report = benchmark_search.collect("", NOW, CUTOFF, include_rss=False)
    assert articles == [] and report["status"] == "not_configured"


def test_collect_handles_network_failure_gracefully(monkeypatch):
    def failing_post(*args, **kwargs):
        raise TimeoutError("Gemini search timed out")

    monkeypatch.setattr(benchmark_search, "collect_strategic_publications", failing_post)
    monkeypatch.setattr(benchmark_search, "collect_google_news_rss", lambda *args, **kwargs: [])
    articles, report = benchmark_search.collect("", NOW, CUTOFF)
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
    assert count == 0
    assert seeds[0]["description"] == ""
    assert "corroborating_sources" not in seeds[0]


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
    aci_traffic_report = {
        "title": "ACI World Confirms Top 10 Busiest Airports as Global Passenger Demand Surges",
        "link": "https://aci.aero/news-and-resources/publications/world-airport-traffic-report-2026/",
        "source": "ACI World",
    }
    airbus_gmf = {
        "title": "Airbus Forecasts Demand for 42,000 New Aircraft by 2045",
        "link": "https://www.airbus.com/en/products-services/commercial-aircraft/market/global-market-forecast",
        "source": "Airbus",
    }
    icao_traffic_data = {
        "title": "ICAO Confirms Global Air Passenger Traffic Surpasses Pre-Pandemic Levels",
        "link": "https://www.icao.int/news/pages/air-transport-monthly-report-2026.aspx",
        "source": "ICAO",
    }
    faa_forecast = {
        "title": "FAA Aerospace Forecast Projects Steady Growth in Commercial Fleet Through 2045",
        "link": "https://www.faa.gov/data_research/aviation/aerospace_forecasts/report-2026",
        "source": "FAA",
    }
    oliver_wyman_mro = {
        "title": "Oliver Wyman Global Fleet and MRO Forecast Details Supply Chain and Engine Bottlenecks",
        "link": "https://www.oliverwyman.com/our-expertise/insights/2026/global-fleet-and-mro-forecast.html",
        "source": "Oliver Wyman",
    }
    breaking_news = {
        "title": "United Airlines warns rising jet fuel costs could hit Q2 earnings",
        "link": "https://www.reuters.com/business/aerospace-defense/united-airlines-warns-fuel-costs-2026-10-17/",
        "source": "Reuters",
    }
    assert story_lifecycle.is_strategic_report(boeing_cmo) is True
    assert story_lifecycle.is_strategic_report(eurocontrol) is True
    assert story_lifecycle.is_strategic_report(iata_new_report) is True
    assert story_lifecycle.is_strategic_report(aci_traffic_report) is True
    assert story_lifecycle.is_strategic_report(airbus_gmf) is True
    assert story_lifecycle.is_strategic_report(icao_traffic_data) is True
    assert story_lifecycle.is_strategic_report(faa_forecast) is True
    assert story_lifecycle.is_strategic_report(oliver_wyman_mro) is True
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


def test_morning_deep_reset_at_08_local_and_subsequent_3h_appends():
    from api import story_lifecycle

    # 02:00 UTC = 05:00 Istanbul (pre-08:00 early run)
    t_05_local = datetime(2026, 10, 18, 2, 0, tzinfo=timezone.utc)
    # 05:00 UTC = 08:00 Istanbul (morning deep reset window)
    t_08_local = datetime(2026, 10, 18, 5, 0, tzinfo=timezone.utc)
    # 08:00 UTC = 11:00 Istanbul (subsequent 3-hour run)
    t_11_local = datetime(2026, 10, 18, 8, 0, tzinfo=timezone.utc)

    assert story_lifecycle.is_morning_deep_window(t_05_local) is False
    assert story_lifecycle.is_morning_deep_window(t_08_local) is True
    assert story_lifecycle.is_morning_deep_window(t_11_local) is False

    early_story = {
        "story_id": "early-1",
        "headline": "Overnight Regional Carrier Schedule Change",
        "relevance_score": 55.0,
        "published_at_iso": "2026-10-18T01:30:00Z",
        "sources": [{"name": "Reuters", "url": "https://www.reuters.com/early-1", "title": "Early"}],
        "original_source": {"url": "https://www.reuters.com/early-1", "source_name": "Reuters"},
    }
    strategic_report = {
        "story_id": "report-boeing",
        "headline": "Boeing Commercial Market Outlook 2026-2045",
        "relevance_score": 82.0,
        "is_strategic_report": True,
        "published_at_iso": "2026-10-18T01:00:00Z",
        "sources": [{"name": "Boeing", "url": "https://www.boeing.com/commercial/market/commercial-market-outlook", "title": "Boeing CMO"}],
        "original_source": {"url": "https://www.boeing.com/commercial/market/commercial-market-outlook", "source_name": "Boeing"},
    }
    day_05 = story_lifecycle.build_day(
        None,
        None,
        {"daily": {"mode": "daily", "stories": [early_story, strategic_report]}},
        t_05_local,
    )
    assert {s["story_id"] for s in day_05["stories"]} == {"early-1", "report-boeing"}
    assert "morning_reset_at" not in day_05

    # The 08:00 deep scan preserves previously stored news as well as strategic reports
    morning_story = {
        "story_id": "morning-1",
        "headline": "Lufthansa Group Posts Record Q3 Operating Profit",
        "relevance_score": 78.0,
        "published_at_iso": "2026-10-18T04:45:00Z",
        "sources": [{"name": "Reuters", "url": "https://www.reuters.com/morning-1", "title": "Lufthansa Q3"}],
        "original_source": {"url": "https://www.reuters.com/morning-1", "source_name": "Reuters"},
    }
    day_08 = story_lifecycle.build_day(
        day_05,
        None,
        {"daily": {"mode": "daily", "morning_deep_scan": True, "stories": [morning_story]}},
        t_08_local,
    )
    assert {s["story_id"] for s in day_08["stories"]} == {"early-1", "morning-1", "report-boeing"}
    assert day_08.get("morning_reset_at") == story_lifecycle.to_iso(t_08_local)

    # At 11:00 Istanbul (next 3-hour scan), new stories are appended onto the 08:00 stories
    midday_story = {
        "story_id": "midday-1",
        "headline": "Turkish Airlines Expands Asian Widebody Frequencies",
        "relevance_score": 74.0,
        "published_at_iso": "2026-10-18T07:30:00Z",
        "sources": [{"name": "Turkish Airlines", "url": "https://www.turkishairlines.com/midday-1", "title": "THY Asia"}],
        "original_source": {"url": "https://www.turkishairlines.com/midday-1", "source_name": "Turkish Airlines"},
    }
    day_11 = story_lifecycle.build_day(
        day_08,
        None,
        {"daily": {"mode": "daily", "morning_deep_scan": False, "stories": [midday_story]}},
        t_11_local,
    )
    assert {s["story_id"] for s in day_11["stories"]} == {"early-1", "morning-1", "midday-1", "report-boeing"}
    assert day_11.get("morning_reset_at") == story_lifecycle.to_iso(t_08_local)


def test_collect_google_news_rss_unshortens_links_and_ingests_analyst_radar(monkeypatch):
    rss_xml = """<rss version="2.0"><channel>
      <item>
        <title>Boeing 737 MAX certification flights pick up pace - Reuters</title>
        <link>https://news.google.com/rss/articles/CBMi_test123</link>
        <pubDate>Sun, 18 Oct 2026 08:00:00 GMT</pubDate>
        <description>Flight tests continue for European and FAA review.</description>
        <source url="https://www.reuters.com">Reuters</source>
      </item>
      <item>
        <title>The Air Current: New FAA AD issued for high-cycle narrowbodies</title>
        <link>https://theaircurrent.com/aviation-safety/new-faa-ad-narrowbody</link>
        <pubDate>Sun, 18 Oct 2026 08:15:00 GMT</pubDate>
        <description>FAA directive affects fleet engines and airframes.</description>
        <source url="https://theaircurrent.com">The Air Current</source>
      </item>
    </channel></rss>"""

    class MockResponse:
        def __init__(self, data):
            self.data = data.encode("utf-8") if isinstance(data, str) else data
        def read(self):
            return self.data
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def mock_opener(req, timeout=None, context=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "news.google.com/rss/search" in url:
            return MockResponse(rss_xml)
        if "news.google.com/rss/articles" in url:
            return MockResponse('<div data-n-a-sg="sg1" data-n-a-ts="100"></div>')
        if "batchexecute" in url:
            return MockResponse(')]}\'\n[["wrb.fr","Fbv4je","[\\"garturlres\\",\\"https://www.reuters.com/business/aerospace/boeing-737-max-flights\\"]",null,null,null,"generic"]]')
        raise ValueError("Unexpected url: " + url)

    monkeypatch.setattr(benchmark_search, "GOOGLE_NEWS_QUERIES", (("reuters", "query"),))
    monkeypatch.setattr(benchmark_search, "collection_config", lambda: {"allow_google_news": True})

    articles = benchmark_search.collect_google_news_rss(NOW, CUTOFF, opener=mock_opener)
    assert len(articles) == 2
    reuters_art = next(a for a in articles if "Reuters" in a["source"])
    analyst_art = next(a for a in articles if "The Air Current" in a["source"])

    # Google News opaque redirect link was unshortened to direct publisher URL
    assert reuters_art["link"] == "https://www.reuters.com/business/aerospace/boeing-737-max-flights"

    # Analyst Radar item is tagged as flash alert
    assert analyst_art["is_flash_alert"] is True
    assert analyst_art["source"] == "The Air Current"
    assert analyst_art["tier"] == 2



