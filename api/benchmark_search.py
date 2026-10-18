"""Benchmark & Wire Intelligence collector (Google News RSS + Gemini Google Search Grounding).

Collects recent reports, indices, data bulletins and breaking civil aviation stories from:
1. Mandatory Aviation Intelligence & Benchmark Sources:
   - IdeaWorksCompany (ideaworkscompany.com): Ancillary revenue, a la carte pricing, FFP/loyalty revenue, unbundling trends.
   - OAG (oag.com): Capacity trends, Megahubs indices, connecting banks, On-Time Performance (OTP).
   - Cirium (cirium.com) & ch-aviation (ch-aviation.com): Fleet deliveries, aircraft utilization, GTF/LEAP engine & AOG statistics.
   - IATA (iata.org) & ACI World (aci.aero): Global passenger (RPK) and cargo (CTK) demand, jet fuel crack spread, airport passenger volumes.
   - CAPA Centre for Aviation (centreforaviation.com) & Eurocontrol (eurocontrol.int): Strategic airline analyses, bilateral air service agreements, European slot/ATC delays.
2. Global Financial & Aviation Wire / Press Sources (blocked or without public RSS):
   - Reuters (reuters.com)
   - Bloomberg (bloomberg.com)
   - Financial Times (ft.com)
   - The Wall Street Journal (wsj.com)
   - Associated Press (apnews.com)
   - CNBC (cnbc.com)
   - Aviation Week (aviationweek.com)
   - Nikkei Asia (asia.nikkei.com)
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

try:
    from . import language
except ImportError:
    import language

SOURCE_NAME = "Gemini Benchmark Intelligence (Search Grounded)"
GEMINI_SEARCH_MODEL = "gemini-3.5-flash"
GEMINI_FALLBACK_MODELS = ("gemini-3-flash-preview", "gemini-2.5-pro")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
REQUEST_TIMEOUT_SECONDS = 20
RSS_QUERY_TIMEOUT_SECONDS = 10
MAX_ITEMS_PER_QUERY = 8
MAX_BENCHMARK_ITEMS = 28

BENCHMARK_PUBLISHERS = {
    "ideaworkscompany.com": {
        "name": "IdeaWorksCompany",
        "source_type": "trade_media",
        "official": True,
        "tier": 2,
        "reliability_weight": 0.9,
        "region": "Global",
        "category_hint": "Other areas",
    },
    "oag.com": {
        "name": "OAG",
        "source_type": "trade_media",
        "official": True,
        "tier": 2,
        "reliability_weight": 0.9,
        "region": "Global",
        "category_hint": "Route news",
    },
    "cirium.com": {
        "name": "Cirium",
        "source_type": "trade_media",
        "official": True,
        "tier": 2,
        "reliability_weight": 0.9,
        "region": "Global",
        "category_hint": "Other areas",
    },
    "ch-aviation.com": {
        "name": "ch-aviation",
        "source_type": "trade_media",
        "official": False,
        "tier": 2,
        "reliability_weight": 0.9,
        "region": "Global",
        "category_hint": "European and other global airlines",
    },
    "iata.org": {
        "name": "IATA",
        "source_type": "regulator",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Global",
        "category_hint": "Other areas",
    },
    "aci.aero": {
        "name": "ACI World",
        "source_type": "regulator",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Global",
        "category_hint": "Other areas",
    },
    "centreforaviation.com": {
        "name": "CAPA Centre for Aviation",
        "source_type": "trade_media",
        "official": False,
        "tier": 2,
        "reliability_weight": 0.9,
        "region": "Global",
        "category_hint": "European and other global airlines",
    },
    "eurocontrol.int": {
        "name": "Eurocontrol",
        "source_type": "regulator",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Europe",
        "category_hint": "European and other global airlines",
    },
    "reuters.com": {
        "name": "Reuters",
        "source_type": "mainstream",
        "official": False,
        "tier": 2,
        "reliability_weight": 0.9,
        "region": "Global",
        "category_hint": "European and other global airlines",
    },
    "bloomberg.com": {
        "name": "Bloomberg",
        "source_type": "mainstream",
        "official": False,
        "tier": 2,
        "reliability_weight": 0.9,
        "region": "Global",
        "category_hint": "European and other global airlines",
    },
    "ft.com": {
        "name": "Financial Times",
        "source_type": "mainstream",
        "official": False,
        "tier": 2,
        "reliability_weight": 0.9,
        "region": "Global",
        "category_hint": "European and other global airlines",
    },
    "wsj.com": {
        "name": "The Wall Street Journal",
        "source_type": "mainstream",
        "official": False,
        "tier": 2,
        "reliability_weight": 0.9,
        "region": "Global",
        "category_hint": "European and other global airlines",
    },
    "apnews.com": {
        "name": "Associated Press",
        "source_type": "mainstream",
        "official": False,
        "tier": 2,
        "reliability_weight": 0.85,
        "region": "Global",
        "category_hint": "European and other global airlines",
    },
    "cnbc.com": {
        "name": "CNBC",
        "source_type": "mainstream",
        "official": False,
        "tier": 2,
        "reliability_weight": 0.85,
        "region": "Global",
        "category_hint": "European and other global airlines",
    },
    "aviationweek.com": {
        "name": "Aviation Week",
        "source_type": "trade_media",
        "official": False,
        "tier": 2,
        "reliability_weight": 0.9,
        "region": "Global",
        "category_hint": "European and other global airlines",
    },
    "economist.com": {
        "name": "The Economist",
        "source_type": "mainstream",
        "official": False,
        "tier": 2,
        "reliability_weight": 0.85,
        "region": "Global",
        "category_hint": "European and other global airlines",
    },
    "asia.nikkei.com": {
        "name": "Nikkei Asia",
        "source_type": "mainstream",
        "official": False,
        "tier": 2,
        "reliability_weight": 0.85,
        "region": "Asia-Pacific",
        "category_hint": "European and other global airlines",
    },
    # Blocked / 403 / Timeout Official Airline Newsrooms & Investor Relations
    "turkishairlines.com": {
        "name": "Turkish Airlines",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Turkey",
        "category_hint": "Turkey / THY and Turkish aviation",
        "airline": "Turkish Airlines",
        "airline_code": "TK",
    },
    "iairgroup.com": {
        "name": "IAG Newsroom",
        "source_type": "airline_ir",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Europe",
        "category_hint": "European and other global airlines",
        "airline": "International Airlines Group",
        "airline_code": "IB",
    },
    "airfranceklm.com": {
        "name": "Air France-KLM",
        "source_type": "airline_ir",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Europe",
        "category_hint": "European and other global airlines",
        "airline": "Air France-KLM",
        "airline_code": "AF",
    },
    "qatarairways.com": {
        "name": "Qatar Airways",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Middle East",
        "category_hint": "European and other global airlines",
        "airline": "Qatar Airways",
        "airline_code": "QR",
    },
    "etihad.com": {
        "name": "Etihad Airways",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Middle East",
        "category_hint": "European and other global airlines",
        "airline": "Etihad Airways",
        "airline_code": "EY",
    },
    "united.com": {
        "name": "United Airlines",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "North America",
        "category_hint": "European and other global airlines",
        "airline": "United Airlines",
        "airline_code": "UA",
    },
    "swamedia.com": {
        "name": "Southwest Airlines",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "North America",
        "category_hint": "European and other global airlines",
        "airline": "Southwest Airlines",
        "airline_code": "WN",
    },
    "aircanada.com": {
        "name": "Air Canada",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "North America",
        "category_hint": "European and other global airlines",
        "airline": "Air Canada",
        "airline_code": "AC",
    },
    "qantasnewsroom.com.au": {
        "name": "Qantas",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Asia-Pacific",
        "category_hint": "European and other global airlines",
        "airline": "Qantas",
        "airline_code": "QF",
    },
    "singaporeair.com": {
        "name": "Singapore Airlines",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Asia-Pacific",
        "category_hint": "European and other global airlines",
        "airline": "Singapore Airlines",
        "airline_code": "SQ",
    },
    "ana.co.jp": {
        "name": "ANA Group",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Asia-Pacific",
        "category_hint": "European and other global airlines",
        "airline": "ANA",
        "airline_code": "NH",
    },
    "jal.co.jp": {
        "name": "Japan Airlines",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Asia-Pacific",
        "category_hint": "European and other global airlines",
        "airline": "Japan Airlines",
        "airline_code": "JL",
    },
    "goindigo.in": {
        "name": "IndiGo",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Asia-Pacific",
        "category_hint": "European and other global airlines",
        "airline": "IndiGo",
        "airline_code": "6E",
    },
    "airindia.com": {
        "name": "Air India",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Asia-Pacific",
        "category_hint": "European and other global airlines",
        "airline": "Air India",
        "airline_code": "AI",
    },
    "jetblue.com": {
        "name": "JetBlue",
        "source_type": "airline_ir",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "North America",
        "category_hint": "European and other global airlines",
        "airline": "JetBlue",
        "airline_code": "B6",
    },
    "latamairlines.com": {
        "name": "LATAM Airlines",
        "source_type": "airline_ir",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Latin America",
        "category_hint": "European and other global airlines",
        "airline": "LATAM Airlines",
        "airline_code": "LA",
    },
    "copaair.com": {
        "name": "Copa Airlines",
        "source_type": "airline_ir",
        "official": True,
        "tier": 1,
        "reliability_weight": 1.0,
        "region": "Latin America",
        "category_hint": "European and other global airlines",
        "airline": "Copa Airlines",
        "airline_code": "CM",
    },
    # Blocked / Key OEMs & Engine Manufacturers
    "airbus.com": {
        "name": "Airbus",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 0.95,
        "region": "Europe",
        "category_hint": "European and other global airlines",
    },
    "boeing.com": {
        "name": "Boeing",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 0.95,
        "region": "North America",
        "category_hint": "European and other global airlines",
    },
    "embraer.com": {
        "name": "Embraer",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 0.95,
        "region": "Latin America",
        "category_hint": "European and other global airlines",
    },
    "rtx.com": {
        "name": "RTX / Pratt & Whitney",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 0.95,
        "region": "North America",
        "category_hint": "Other areas",
    },
    "safran-group.com": {
        "name": "Safran",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 0.95,
        "region": "Europe",
        "category_hint": "Other areas",
    },
    "rolls-royce.com": {
        "name": "Rolls-Royce",
        "source_type": "airline_newsroom",
        "official": True,
        "tier": 1,
        "reliability_weight": 0.95,
        "region": "Europe",
        "category_hint": "Other areas",
    },
    # Blocked Press Release Wires & Travel Tech Media
    "prnewswire.com": {
        "name": "PR Newswire",
        "source_type": "trade_media",
        "official": False,
        "tier": 2,
        "reliability_weight": 0.85,
        "region": "Global",
        "category_hint": "European and other global airlines",
    },
    "globenewswire.com": {
        "name": "GlobeNewswire",
        "source_type": "trade_media",
        "official": False,
        "tier": 2,
        "reliability_weight": 0.85,
        "region": "Global",
        "category_hint": "European and other global airlines",
    },
    "businesswire.com": {
        "name": "Business Wire",
        "source_type": "trade_media",
        "official": False,
        "tier": 2,
        "reliability_weight": 0.85,
        "region": "Global",
        "category_hint": "European and other global airlines",
    },
    "phocuswire.com": {
        "name": "PhocusWire",
        "source_type": "trade_media",
        "official": False,
        "tier": 2,
        "reliability_weight": 0.85,
        "region": "Global",
        "category_hint": "Other areas",
    },
}

PUBLISHER_BY_NAME = {
    meta["name"].lower(): meta for meta in BENCHMARK_PUBLISHERS.values()
}
PUBLISHER_BY_NAME.update({
    "capa": BENCHMARK_PUBLISHERS["centreforaviation.com"],
    "ideaworks": BENCHMARK_PUBLISHERS["ideaworkscompany.com"],
    "aci": BENCHMARK_PUBLISHERS["aci.aero"],
    "oag aviation": BENCHMARK_PUBLISHERS["oag.com"],
    "bloomberg.com": BENCHMARK_PUBLISHERS["bloomberg.com"],
    "wsj": BENCHMARK_PUBLISHERS["wsj.com"],
    "wall street journal": BENCHMARK_PUBLISHERS["wsj.com"],
    "ft": BENCHMARK_PUBLISHERS["ft.com"],
    "ap": BENCHMARK_PUBLISHERS["apnews.com"],
    "ap news": BENCHMARK_PUBLISHERS["apnews.com"],
    "nikkei": BENCHMARK_PUBLISHERS["asia.nikkei.com"],
    "pratt & whitney": BENCHMARK_PUBLISHERS["rtx.com"],
    "rtx": BENCHMARK_PUBLISHERS["rtx.com"],
    "latam.com": BENCHMARK_PUBLISHERS["latamairlines.com"],
})

DISALLOWED_HOSTS = {"youtube.com", "youtu.be", "facebook.com", "instagram.com", "tiktok.com"}

CIVIL_AVIATION_TITLE_PATTERN = re.compile(
    r"\b(?:"
    r"airline|airlines|airways|airliner|airliners|aviation|"
    r"flight|flights|flying|flier|flyer|frequent-flier|frequent\s+flyer|"
    r"airport|airports|airspace|air\s+traffic|atc|faa|easa|iata|icao|eurocontrol|"
    r"oag|cirium|ideaworks|ideaworkscompany|capa|ch-aviation|"
    r"airbus|boeing|embraer|atr|(?:737|747|767|777|787)s?|"
    r"(?:a220|a319|a320|a321|a321xlr|a330|a350|a380)s?|max\s+10|max\s+8|max\s+9|"
    r"narrowbody|widebody|wet\s+lease|wet-lease|acmi|ancillary|unbundl\w*|megahubs?|"
    r"commercial\s+market\s+outlook|global\s+market\s+forecast|seven-year\s+forecast|seven‑year\s+forecast|"
    r"cask|rask|aog|gtf|leap-1[ab]?|cfm|pratt\s+&\s+whitney|rolls-royce|"
    r"lufthansa|delta\s+air|united\s+airlines|american\s+airlines|southwest|ryanair|"
    r"easyjet|wizz\s+air|turkish\s+airlines|thy|pegasus|emirates|qatar\s+airways|"
    r"etihad|klm|air\s+france|iag|british\s+airways|iberia|tap\s+air|tap\s+portugal|qantas|"
    r"singapore\s+airlines|cathay|air\s+canada|indigo|air\s+india|latam|copa\s+airlines|"
    r"jetblue|alaska\s+air|spirit\s+airlines|frontier\s+airlines|vietnam\s+airlines|"
    r"korean\s+air|all\s+nippon|japan\s+airlines|avelo"
    r")\b",
    flags=re.IGNORECASE,
)

OFF_TOPIC_TITLE_TERMS = (
    "spacex", "starlink", "tesla", "roadster", "golf", "asian tour", "nba", "nfl",
    "premier league", "crypto", "bitcoin", "streaming subscription",
    "things to watch in the stock market", "webinar |", "aviation daily,",
)


def is_civil_aviation_item(title, description="", publisher=None):
    lower_title = str(title or "").lower()
    if any(term in lower_title for term in OFF_TOPIC_TITLE_TERMS):
        return False
    publisher = publisher or {}
    if publisher.get("source_type") in {"regulator", "trade_media", "airline_newsroom", "airline_ir"}:
        combined = f"{title or ''} {description or ''}"
        return bool(CIVIL_AVIATION_TITLE_PATTERN.search(combined))
    return bool(CIVIL_AVIATION_TITLE_PATTERN.search(str(title or "")))


GOOGLE_NEWS_QUERIES = (
    ("reuters", "site:reuters.com (airline OR airlines OR aviation OR airbus OR boeing OR airport) when:2d"),
    ("bloomberg", "site:bloomberg.com (airline OR airlines OR aviation OR airbus OR boeing OR airport) when:2d"),
    ("ft_wsj", "(site:ft.com OR site:wsj.com) (airline OR airlines OR aviation OR airbus OR boeing) when:2d"),
    ("cnbc_ap", "(site:cnbc.com OR site:apnews.com) (airline OR airlines OR aviation OR airbus OR boeing) when:2d"),
    ("trade_intel", "(site:aviationweek.com OR site:ch-aviation.com OR site:centreforaviation.com) (airline OR fleet OR capacity OR route OR engine) when:3d"),
    ("benchmarks", "(site:oag.com OR site:cirium.com OR site:ideaworkscompany.com OR OAG OR Cirium OR IdeaWorksCompany) (airline OR aviation OR ancillary OR megahubs OR fleet OR capacity) when:7d"),
    (
        "outlooks_forecasts",
        "(\"Commercial Market Outlook\" OR \"Global Market Forecast\" OR \"Eurocontrol Forecast\" "
        "OR site:eurocontrol.int/publication OR \"Megahubs\" OR \"Yearbook of Ancillary Revenue\") when:30d",
    ),
    (
        "blocked_airlines",
        "(site:turkishairlines.com OR site:iairgroup.com OR site:airfranceklm.com OR site:qatarairways.com OR site:etihad.com "
        "OR site:united.com OR site:swamedia.com OR site:aircanada.com OR site:qantasnewsroom.com.au OR site:singaporeair.com "
        "OR site:jal.co.jp OR site:goindigo.in OR site:airindia.com OR site:jetblue.com OR site:latamairlines.com OR site:copaair.com) "
        "(flight OR route OR fleet OR aircraft OR results OR passenger OR cargo) when:3d",
    ),
    (
        "oems_and_wires",
        "(site:airbus.com OR site:boeing.com OR site:embraer.com OR site:rtx.com OR site:safran-group.com OR site:rolls-royce.com "
        "OR site:prnewswire.com OR site:globenewswire.com OR site:businesswire.com) "
        "(airline OR airlines OR airbus OR boeing OR aircraft OR fleet OR engine OR route) when:2d",
    ),
)


def _clean_html_text(raw):
    if not raw:
        return ""
    text = re.sub(r"<.*?>", " ", str(raw))
    return " ".join(unescape(text).split()).strip()


def build_search_prompt(now, cutoff, seed_articles=None):
    today_str = now.strftime("%Y-%m-%d")
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    seed_block = ""
    if seed_articles:
        lines = [
            f"{idx}. [{item.get('source', '')}] {item.get('title', '')}"
            for idx, item in enumerate(seed_articles[:16])
        ]
        seed_block = (
            "\nTASK 1 — CROSS-SOURCE CONTEXT ENRICHMENT FOR DISCOVERED HEADLINES:\n"
            "Search Google for each headline below across open press releases, wire reports, and aviation trade media. "
            "For each headline, return in `enrichments` a 2-4 sentence factual summary containing the exact numbers, "
            "aircraft/engine counts, dollar/euro amounts, percentages, routes, frequencies, dates, and named carriers reported.\n"
            + "\n".join(lines)
            + "\n"
        )
    return f"""You are an aviation intelligence research engine with Google Search access.
Today is {today_str}. Search Google for newly published aviation reports, indices, data bulletins, flagship market outlooks/forecasts, official airline/OEM announcements, and breaking airline industry news published between {cutoff_str} and {today_str}.
{seed_block}
TASK 2 — DISCOVER NEW REPORTS, FLAGSHIP OUTLOOKS & BREAKING ITEMS FROM PRIORITY SOURCE GROUPS:
GROUP A — Mandatory Aviation Intelligence, Benchmark & Flagship Forecast Sources:
1. IdeaWorksCompany (ideaworkscompany.com): Ancillary revenue yearbooks, a la carte pricing reports, frequent flyer program (FFP) / loyalty revenues, unbundling trends.
2. OAG (oag.com): Capacity trends, Megahubs indices, connecting banks, on-time performance (OTP).
3. Cirium (cirium.com) & ch-aviation (ch-aviation.com): Fleet deliveries, Fleet Forecast, aircraft utilization rates, GTF/LEAP engine inspections, AOG statistics, wet-lease / ACMI capacity.
4. IATA (iata.org) & ACI World (aci.aero): Global passenger demand (RPK), air cargo demand (CTK), jet fuel crack spread, airport passenger volumes, Global Outlook for Air Transport.
5. CAPA Centre for Aviation (centreforaviation.com) & Eurocontrol (eurocontrol.int): EUROCONTROL Seven-Year Forecast (e.g. 2026-2032), European Aviation Overview, strategic airline analyses, bilateral air service agreements, European slot/ATC delays, hub-bypass dynamics at slot-constrained hubs (LHR, CDG, AMS, FRA), and fleet unit cost (CASK/RASK) developments for A321XLR, A350, B787, E2, B737 MAX.
6. OEM Flagship Market Outlooks: Boeing Commercial Market Outlook (CMO, boeing.com/commercial/market/commercial-market-outlook) and Airbus Global Market Forecast (GMF, airbus.com).

GROUP B — Global Wire, Financial, Official Airline/OEM & Press Wire Sources (Civil Aviation / Airlines Only):
7. Reuters (reuters.com), Bloomberg (bloomberg.com), Financial Times (ft.com), The Wall Street Journal (wsj.com), Associated Press (apnews.com), CNBC (cnbc.com), Aviation Week (aviationweek.com), Nikkei Asia (asia.nikkei.com).
8. Official Airline & OEM Newsrooms / Press Wires: Turkish Airlines (turkishairlines.com), IAG (iairgroup.com), Air France-KLM (airfranceklm.com), Qatar Airways (qatarairways.com), Etihad (etihad.com), United (united.com), Qantas, IndiGo, Air India, LATAM, Airbus (airbus.com), Boeing (boeing.com), Embraer (embraer.com), RTX/Pratt & Whitney (rtx.com), Safran (safran-group.com), Rolls-Royce (rolls-royce.com), PR Newswire (prnewswire.com), GlobeNewswire (globenewswire.com), Business Wire (businesswire.com).

Rules:
- Include ONLY real, verifiable civil aviation / airline items published between {cutoff_str} and {today_str}. Never invent URLs, titles, dates, or figures.
- Include concrete numerical figures (RPK, CTK, ASK, CASK, RASK, OTP %, AOG counts, ancillary revenue $, capacity %, MCT, slot counts, order counts, revenue/profit figures) in `description` whenever stated by the source.
- Return ONLY a valid JSON object with this exact schema (no markdown commentary outside the JSON):
{{
  "enrichments": [
    {{
      "index": 0,
      "description": "2-4 factual sentences with exact numbers, routes, aircraft/engine counts, deal value, and dates from open coverage.",
      "corroborating_sources": ["Publisher A", "Publisher B"]
    }}
  ],
  "items": [
    {{
      "title": "Exact headline or report title",
      "url": "https://direct-url-to-the-report-or-article",
      "source_name": "Reuters | Bloomberg | Financial Times | The Wall Street Journal | Aviation Week | Turkish Airlines | Airbus | Boeing | RTX / Pratt & Whitney | IdeaWorksCompany | OAG | Cirium | ch-aviation | IATA | ACI World | CAPA Centre for Aviation | Eurocontrol",
      "published_at": "YYYY-MM-DD",
      "description": "2-4 factual sentences summarizing the findings, concrete numbers, and commercial/network/fleet implications."
    }}
  ]
}}"""


def _extract_json_object(raw_text):
    if not raw_text:
        return {}
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.IGNORECASE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def resolve_publisher_meta(url, source_name=""):
    parsed = urllib.parse.urlparse(str(url or ""))
    host = (parsed.hostname or "").lower().removeprefix("www.")
    for domain, meta in BENCHMARK_PUBLISHERS.items():
        if host == domain or host.endswith("." + domain):
            return meta
    normalized_name = str(source_name or "").strip().lower()
    for key, meta in PUBLISHER_BY_NAME.items():
        if key == normalized_name or key in normalized_name:
            return meta
    return None


def _parse_date_in_window(date_str, now, cutoff):
    if not date_str:
        return None
    raw = str(date_str).strip()
    parsed = None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        parsed = None
    if parsed is None:
        for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y"):
            try:
                parsed = datetime.strptime(raw[:10] if fmt == "%Y-%m-%d" else raw, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(hour=now.hour, minute=now.minute, tzinfo=timezone.utc)
    cutoff_floor = cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
    if parsed < cutoff_floor or parsed > now.replace(hour=23, minute=59, second=59):
        return None
    return parsed


def _grounding_urls(response):
    """Extract grounded web URLs from Gemini groundingMetadata when present."""
    urls = []
    candidates = response.get("candidates") if isinstance(response, dict) else []
    for candidate in candidates if isinstance(candidates, list) else []:
        metadata = candidate.get("groundingMetadata") if isinstance(candidate, dict) else {}
        chunks = metadata.get("groundingChunks") if isinstance(metadata, dict) else []
        for chunk in chunks if isinstance(chunks, list) else []:
            web = chunk.get("web") if isinstance(chunk, dict) else {}
            uri = web.get("uri") if isinstance(web, dict) else ""
            if isinstance(uri, str) and uri.startswith(("http://", "https://")):
                urls.append(uri)
    return urls


def _is_allowed_url(url):
    parsed = urllib.parse.urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return not any(host == blocked or host.endswith("." + blocked) for blocked in DISALLOWED_HOSTS)


def _build_article(title, url, description, publisher, published_at, now, classify_topics_fn=None, headline_only=False):
    try:
        from . import story_lifecycle as _story_lifecycle
    except ImportError:
        import story_lifecycle as _story_lifecycle
    topics = classify_topics_fn(f"{title} {description}") if classify_topics_fn else []
    effective_ts = max(
        published_at.timestamp(),
        now.replace(hour=0, minute=1, second=0, microsecond=0).timestamp(),
    )
    article = {
        "title": title,
        "link": url,
        "description": description[:300] if headline_only else description[:1200],
        "source": publisher["name"],
        "language": language.detect_language(f"{title} {description}"),
        "category_hint": publisher["category_hint"],
        "source_type": publisher["source_type"],
        "official": publisher["official"],
        "airline": publisher.get("airline", ""),
        "airline_code": publisher.get("airline_code", ""),
        "license_required": False,
        "license_status": "public",
        "source_id": None,
        "region": publisher["region"],
        "tier": publisher["tier"],
        "reliability_weight": publisher["reliability_weight"],
        "topics": topics,
        "pub_date": published_at.strftime("%d %b %H:%M"),
        "timestamp": effective_ts,
        "via_benchmark_search": True,
    }
    if headline_only:
        article["basis"] = "headline_only"
    if _story_lifecycle.is_strategic_report(article):
        article["strategic_publication"] = True
        article["is_strategic_report"] = True
    return article


def fetch_google_news_query(query, now, cutoff, classify_topics_fn=None, opener=urllib.request.urlopen):
    url = GOOGLE_NEWS_RSS_URL.format(query=urllib.parse.quote(query))
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; aviation-briefing-app)"})
    ctx = ssl.create_default_context()
    with opener(request, context=ctx, timeout=RSS_QUERY_TIMEOUT_SECONDS) as response:
        xml_bytes = response.read()
    root = ET.fromstring(xml_bytes)
    articles = []
    for item in root.findall("./channel/item")[:MAX_ITEMS_PER_QUERY]:
        raw_title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date_raw = (item.findtext("pubDate") or "").strip()
        description = _clean_html_text(item.findtext("description") or "")
        source_el = item.find("source")
        source_name = (source_el.text or "").strip() if source_el is not None else ""
        source_url = (source_el.attrib.get("url") or "").strip() if source_el is not None else ""

        if " - " in raw_title:
            title_part, trailing_source = (part.strip() for part in raw_title.rsplit(" - ", 1))
            if not source_name:
                source_name = trailing_source
            raw_title = title_part

        if len(raw_title) < 12 or not _is_allowed_url(link):
            continue
        published_at = _parse_date_in_window(pub_date_raw, now, cutoff)
        if published_at is None:
            continue
        publisher = resolve_publisher_meta(source_url or link, source_name)
        if publisher is None:
            continue
        if description.lower().startswith(raw_title.lower()):
            description = description[len(raw_title):].strip(" -–—·")
        if description.lower() == publisher["name"].lower() or len(description) <= len(source_name) + 3:
            description = ""
        if not is_civil_aviation_item(raw_title, description, publisher):
            continue
        articles.append(
            _build_article(
                raw_title,
                link,
                description,
                publisher,
                published_at,
                now,
                classify_topics_fn=classify_topics_fn,
                headline_only=publisher["source_type"] == "mainstream",
            )
        )
    return articles


def collect_google_news_rss(now, cutoff, classify_topics_fn=None, opener=urllib.request.urlopen):
    collected = []

    def _run_one(entry):
        _, query = entry
        try:
            return fetch_google_news_query(query, now, cutoff, classify_topics_fn=classify_topics_fn, opener=opener)
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=min(8, len(GOOGLE_NEWS_QUERIES)), thread_name_prefix="benchmark-rss") as pool:
        for batch in pool.map(_run_one, GOOGLE_NEWS_QUERIES):
            collected.extend(batch)
    return collected


CORROBORATION_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "over", "after",
    "amid", "says", "said", "will", "plan", "plans", "set", "new", "its", "their",
    "are", "has", "have", "not", "yet", "soon", "next", "week", "sources", "say",
    "exclusive", "update", "updates", "report", "reports",
}

NUMBER_WORDS = {
    "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
}


def _normalize_number_words(text):
    """Append digit equivalents to number words so narrative.grounded_numbers recognizes both."""
    def _repl(match):
        word = match.group(0)
        digit = NUMBER_WORDS.get(word.lower())
        return f"{word} ({digit})" if digit else word

    return re.sub(r"\b(?:" + "|".join(NUMBER_WORDS) + r")\b", _repl, str(text or ""), flags=re.IGNORECASE)


def _corroboration_tokens(title):
    words = re.findall(r"[A-Za-z0-9€$£-]+", str(title or ""))
    tokens = []
    for word in words:
        clean = word.strip("-").lower()
        if len(clean) < 3 and not any(ch.isdigit() for ch in clean):
            continue
        if clean in CORROBORATION_STOPWORDS:
            continue
        tokens.append(word.strip("-"))
    return tokens[:7]


def corroborate_one_article(article, classify_topics_fn=None, opener=urllib.request.urlopen):
    title = str(article.get("title") or "").strip()
    tokens = _corroboration_tokens(title)
    if len(tokens) < 3:
        return False
    query = " ".join(tokens[:6]) + " when:3d"
    url = GOOGLE_NEWS_RSS_URL.format(query=urllib.parse.quote(query))
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; aviation-briefing-app)"})
    ctx = ssl.create_default_context()
    with opener(request, context=ctx, timeout=RSS_QUERY_TIMEOUT_SECONDS) as response:
        xml_bytes = response.read()
    root = ET.fromstring(xml_bytes)
    base_tokens = {tok.lower() for tok in tokens}
    snippets = []
    corroborating_sources = []
    seen_titles = {title.lower()}
    for item in root.findall("./channel/item")[:6]:
        raw_cand = (item.findtext("title") or "").strip()
        source_el = item.find("source")
        cand_source = (source_el.text or "").strip() if source_el is not None else ""
        if " - " in raw_cand:
            cand_title, trailing_src = (part.strip() for part in raw_cand.rsplit(" - ", 1))
            if not cand_source:
                cand_source = trailing_src
        else:
            cand_title = raw_cand
        if not cand_title or cand_title.lower() in seen_titles:
            continue
        cand_tokens = {tok.lower() for tok in _corroboration_tokens(cand_title)}
        if len(base_tokens & cand_tokens) < 2:
            continue
        seen_titles.add(cand_title.lower())
        normalized_title = _normalize_number_words(cand_title)
        snippets.append(f"[{cand_source}] {normalized_title}" if cand_source else normalized_title)
        if cand_source and cand_source not in corroborating_sources:
            corroborating_sources.append(cand_source)
        if len(snippets) >= 3:
            break

    if not snippets:
        return False
    max_len = 300 if article.get("basis") == "headline_only" else 1200
    prefix = _normalize_number_words(title)
    combined = f"{prefix} | " + " | ".join(snippets)
    article["description"] = combined[:max_len]
    if corroborating_sources:
        article["corroborating_sources"] = corroborating_sources[:4]
    if classify_topics_fn:
        article["topics"] = classify_topics_fn(f"{title} {article['description']}")
    return True


def corroborate_thin_articles(articles, classify_topics_fn=None, opener=urllib.request.urlopen):
    thin = [article for article in articles if len(str(article.get("description") or "")) < 60][:24]
    if not thin:
        return 0

    def _run(article):
        try:
            return corroborate_one_article(article, classify_topics_fn=classify_topics_fn, opener=opener)
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=min(8, len(thin)), thread_name_prefix="benchmark-corroborate") as pool:
        results = list(pool.map(_run, thin))
    return sum(1 for ok in results if ok)


STRATEGIC_PUBLICATION_PAGES = (
    (
        "https://www.boeing.com/commercial/market/commercial-market-outlook",
        "Boeing",
        "Boeing Commercial Market Outlook",
    ),
    (
        "https://www.eurocontrol.int/publication/eurocontrol-forecast-2026-2032",
        "Eurocontrol",
        "EUROCONTROL Forecast Update 2026-2032",
    ),
    (
        "https://www.airbus.com/en/products-services/commercial-aircraft/market/global-market-forecast",
        "Airbus",
        "Airbus Global Market Forecast",
    ),
    (
        "https://www.oag.com/megahubs-airports-2025",
        "OAG",
        "OAG Megahubs Global Airport Connectivity Index",
    ),
)

PUBLICATION_BOILERPLATE_TERMS = (
    "cookie",
    "privacy policy",
    "terms of use",
    "all rights reserved",
    "subscribe",
    "click on any item",
    "download button",
    "javascript enabled",
    "follow our director general",
    "what are you looking for?",
    "eurofighter typhoon",
    "uncrewed aerial systems",
)

QUANTITATIVE_BLOCK_PATTERN = re.compile(
    r"(?:\d+(?:\.\d+)?%|\b\d{1,3}(?:,\d{3})+\b|\b\d+(?:\.\d+)?\s*(?:million|billion|airplanes|aircraft|flights|jets|airports|airlines)\b)",
    flags=re.IGNORECASE,
)


def _fetch_html_page(url, opener=urllib.request.urlopen, timeout=RSS_QUERY_TIMEOUT_SECONDS):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    ctx = ssl.create_default_context()
    with opener(request, context=ctx, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_publication_page(html_text, fallback_title="", brand_prefix=""):
    """Extract title and quantitative summary paragraphs from a flagship publication HTML page."""
    if not html_text:
        return "", ""
    og_title_m = re.search(
        r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)[\"']",
        html_text,
        flags=re.IGNORECASE,
    ) or re.search(
        r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+property=[\"']og:title[\"']",
        html_text,
        flags=re.IGNORECASE,
    )
    og_desc_m = re.search(
        r"<meta[^>]+(?:property=[\"']og:description[\"']|name=[\"']description[\"'])[^>]+content=[\"']([^\"']+)[\"']",
        html_text,
        flags=re.IGNORECASE,
    ) or re.search(
        r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+(?:property=[\"']og:description[\"']|name=[\"']description[\"'])",
        html_text,
        flags=re.IGNORECASE,
    )

    body = re.sub(
        r"<(?:nav|header|footer|script|style|noscript|form)\b[^>]*>.*?</(?:nav|header|footer|script|style|noscript|form)>",
        " ",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    h1_m = re.search(r"<h1\b[^>]*>(.*?)</h1>", body, flags=re.IGNORECASE | re.DOTALL)
    doc_title_m = re.search(r"<title\b[^>]*>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
    title = (
        _clean_html_text(og_title_m.group(1))
        if og_title_m
        else (_clean_html_text(h1_m.group(1)) if h1_m else fallback_title)
    )
    title = re.sub(r"\s*\|\s*(?:EUROCONTROL|Airbus|Boeing|OAG).*$", "", title, flags=re.IGNORECASE).strip()
    if doc_title_m:
        doc_title = re.sub(
            r"\s*\|\s*(?:EUROCONTROL|Airbus|Boeing|OAG).*$",
            "",
            _clean_html_text(doc_title_m.group(1)),
            flags=re.IGNORECASE,
        ).strip()
        if doc_title and title and title.lower() in doc_title.lower() and len(doc_title) > len(title):
            title = doc_title

    if not re.search(r"202[5-9]", title):
        for h_m in re.finditer(r"<(?:h2|h3|h4)\b[^>]*>(.*?)</(?:h2|h3|h4)>", body, flags=re.IGNORECASE | re.DOTALL):
            htxt = _clean_html_text(h_m.group(1))
            if (
                12 <= len(htxt) < 75
                and re.search(r"202[5-9]\s*[-–]\s*20[345][0-9]", htxt)
                and re.search(r"\b(?:outlook|forecast)\b", htxt, flags=re.IGNORECASE)
            ):
                title = htxt
                break

    if not title or title.lower() in {"discover the most connected airports in the world"}:
        title = fallback_title or title
    if brand_prefix and brand_prefix.lower() not in title.lower():
        title = f"{brand_prefix} {title}".strip()

    blocks = []
    if og_desc_m:
        desc_meta = _clean_html_text(og_desc_m.group(1))
        if len(desc_meta) >= 40 and not any(term in desc_meta.lower() for term in PUBLICATION_BOILERPLATE_TERMS):
            blocks.append(desc_meta)

    body = re.sub(r"<br\s*/?>", "</p><p>", body, flags=re.IGNORECASE)
    for m in re.finditer(r"<(?:p|li)\b[^>]*>(.*?)</(?:p|li)>", body, flags=re.IGNORECASE | re.DOTALL):
        txt = _clean_html_text(m.group(1))
        if len(txt) < 40 or len(txt) > 900:
            continue
        lower_txt = txt.lower()
        if any(term in lower_txt for term in PUBLICATION_BOILERPLATE_TERMS):
            continue
        if txt not in blocks:
            blocks.append(txt)

    if not blocks:
        return title, ""

    scored = sorted(
        enumerate(blocks),
        key=lambda pair: (
            1 if QUANTITATIVE_BLOCK_PATTERN.search(pair[1]) else 0,
            -pair[0],
        ),
        reverse=True,
    )
    quant_indices = sorted(idx for idx, blk in scored if QUANTITATIVE_BLOCK_PATTERN.search(blk))
    other_indices = sorted(idx for idx, blk in scored if not QUANTITATIVE_BLOCK_PATTERN.search(blk))
    ordered_indices = (quant_indices + other_indices)[:6]
    description = _normalize_number_words(" ".join(blocks[idx] for idx in ordered_indices))[:1200]
    return title, description


def extract_ideaworks_reports(html_text, max_reports=2):
    """Extract recent reports (title, url, description) from IdeaWorksCompany reports index HTML."""
    if not html_text:
        return []
    body = re.sub(
        r"<(?:nav|header|footer|script|style|noscript|form)\b[^>]*>.*?</(?:nav|header|footer|script|style|noscript|form)>",
        " ",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    heading_matches = list(
        re.finditer(
            r"<h[234]\b[^>]*>\s*<a\b[^>]+href=[\"'](https?://(?:www\.)?ideaworkscompany\.com/[^\"']+)[\"'][^>]*>(.*?)</a>\s*</h[234]>",
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )
    reports = []
    for idx, match in enumerate(heading_matches[:max_reports]):
        link = match.group(1).strip()
        raw_title = _clean_html_text(match.group(2))
        if not raw_title or not link:
            continue
        if "ideaworks" not in raw_title.lower():
            raw_title = f"IdeaWorksCompany: {raw_title}"
        chunk_start = match.end()
        chunk_end = heading_matches[idx + 1].start() if idx + 1 < len(heading_matches) else len(body)
        chunk = re.sub(r"<br\s*/?>", "</p><p>", body[chunk_start:chunk_end], flags=re.IGNORECASE)
        paras = []
        for p_m in re.finditer(r"<(?:p|li)\b[^>]*>(.*?)</(?:p|li)>", chunk, flags=re.IGNORECASE | re.DOTALL):
            ptxt = _clean_html_text(p_m.group(1))
            if len(ptxt) < 40 or any(term in ptxt.lower() for term in PUBLICATION_BOILERPLATE_TERMS):
                continue
            if ptxt not in paras:
                paras.append(ptxt)
        if paras:
            quant_paras = [p for p in paras if QUANTITATIVE_BLOCK_PATTERN.search(p)]
            other_paras = [p for p in paras if not QUANTITATIVE_BLOCK_PATTERN.search(p)]
            ordered_paras = (quant_paras + other_paras)[:4]
            reports.append((raw_title, link, _normalize_number_words(" ".join(ordered_paras))[:1200]))
    return reports


def discover_eurocontrol_publications(opener=urllib.request.urlopen):
    """Discover the latest Eurocontrol Seven-Year Forecast and Weekly European Aviation Overview URLs."""
    discovered = []
    index_specs = (
        ("https://www.eurocontrol.int/library/search?f%5B0%5D=product%3A801", r"/publication/eurocontrol-forecast-(?!archive)[a-z0-9-]+"),
        ("https://www.eurocontrol.int/forecasting", r"/publication/eurocontrol-european-aviation-overview-20\d{2}-week-\d+"),
    )
    for index_url, pattern in index_specs:
        try:
            html_text = _fetch_html_page(index_url, opener=opener)
            match = re.search(pattern, html_text, flags=re.IGNORECASE)
            if match:
                full_url = f"https://www.eurocontrol.int{match.group(0)}"
                if full_url not in discovered:
                    discovered.append(full_url)
        except Exception:
            continue
    return discovered


def collect_strategic_publications(now, cutoff, classify_topics_fn=None, opener=urllib.request.urlopen):
    """Fetch flagship industry outlooks, forecasts, and benchmark reports directly."""
    del cutoff
    pages_to_fetch = list(STRATEGIC_PUBLICATION_PAGES)
    seen_urls = {url for url, _, _ in pages_to_fetch}

    for euro_url in discover_eurocontrol_publications(opener=opener):
        if euro_url not in seen_urls:
            seen_urls.add(euro_url)
            pages_to_fetch.append((euro_url, "Eurocontrol", "EUROCONTROL Aviation Outlook"))

    articles = []

    def _fetch_one(spec):
        url, source_hint, fallback_title = spec
        try:
            html_text = _fetch_html_page(url, opener=opener)
            publisher = resolve_publisher_meta(url, source_hint)
            if publisher is None:
                return None
            title, description = extract_publication_page(
                html_text,
                fallback_title=fallback_title,
                brand_prefix=publisher["name"],
            )
            if len(title) < 12 or len(description) < 40:
                return None
            item = _build_article(
                title,
                url,
                description,
                publisher,
                now,
                now,
                classify_topics_fn=classify_topics_fn,
                headline_only=False,
            )
            item["strategic_publication"] = True
            return item
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=min(6, len(pages_to_fetch)), thread_name_prefix="strategic-pubs") as pool:
        for item in pool.map(_fetch_one, pages_to_fetch):
            if item is not None:
                articles.append(item)

    try:
        iw_html = _fetch_html_page("https://ideaworkscompany.com/reports/", opener=opener)
        iw_pub = BENCHMARK_PUBLISHERS["ideaworkscompany.com"]
        for title, link, desc in extract_ideaworks_reports(iw_html, max_reports=2):
            iw_item = _build_article(
                title,
                link,
                desc,
                iw_pub,
                now,
                now,
                classify_topics_fn=classify_topics_fn,
                headline_only=False,
            )
            iw_item["strategic_publication"] = True
            articles.append(iw_item)
    except Exception:
        pass

    return articles


def post_search_query(api_key, now, cutoff, seed_articles=None, timeout=REQUEST_TIMEOUT_SECONDS):
    prompt_text = build_search_prompt(now, cutoff, seed_articles=seed_articles)
    ctx = ssl.create_default_context()
    last_error = None
    for model_name in (GEMINI_SEARCH_MODEL, *GEMINI_FALLBACK_MODELS):
        payload = {
            "contents": [{"parts": [{"text": prompt_text}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {
                "temperature": 0.1,
                **({"thinkingConfig": {"thinkingBudget": 0}} if "flash" in model_name and "2.5" in model_name else {}),
            },
        }
        request = urllib.request.Request(
            GEMINI_URL.format(model=model_name),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        )
        try:
            with urllib.request.urlopen(request, context=ctx, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in {404, 429, 500, 503}:
                continue
            raise
    raise last_error


def apply_search_enrichment(response, seed_articles, classify_topics_fn=None):
    """Apply search-grounded factual summaries and corroborating sources to thin RSS articles."""
    if not seed_articles or not isinstance(response, dict):
        return 0
    candidates = response.get("candidates") or []
    if not candidates or not isinstance(candidates[0], dict):
        return 0
    parts = (candidates[0].get("content") or {}).get("parts") or []
    raw_text = "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
    parsed_json = _extract_json_object(raw_text)
    enrichments = parsed_json.get("enrichments") if isinstance(parsed_json, dict) else []
    if not isinstance(enrichments, list):
        return 0

    enriched_count = 0
    for entry in enrichments:
        if not isinstance(entry, dict):
            continue
        idx = entry.get("index")
        desc = str(entry.get("description") or "").strip()
        if not isinstance(idx, int) or idx < 0 or idx >= len(seed_articles) or len(desc) < 25:
            continue
        target = seed_articles[idx]
        max_len = 300 if target.get("basis") == "headline_only" else 1200
        target["description"] = _normalize_number_words(desc)[:max_len]
        corroborating = [
            str(src).strip()
            for src in (entry.get("corroborating_sources") or [])
            if isinstance(src, str) and str(src).strip()
        ]
        if corroborating:
            target["corroborating_sources"] = corroborating[:4]
        if classify_topics_fn:
            target["topics"] = classify_topics_fn(f"{target.get('title', '')} {target['description']}")
        enriched_count += 1
    return enriched_count


def parse_search_response(response, now, cutoff, classify_topics_fn=None):
    candidates = response.get("candidates") if isinstance(response, dict) else []
    if not candidates or not isinstance(candidates[0], dict):
        return []
    parts = (candidates[0].get("content") or {}).get("parts") or []
    raw_text = "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
    parsed_json = _extract_json_object(raw_text)
    raw_items = parsed_json.get("items") if isinstance(parsed_json, dict) else []
    if not isinstance(raw_items, list):
        return []

    grounded_uris = _grounding_urls(response)
    articles = []
    seen_urls = set()
    seen_titles = set()
    for index, item in enumerate(raw_items[:MAX_BENCHMARK_ITEMS]):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if (not url.startswith(("http://", "https://"))) and index < len(grounded_uris):
            url = grounded_uris[index]
        if len(title) < 12 or not _is_allowed_url(url):
            continue
        title_key = title.lower()
        if url in seen_urls or title_key in seen_titles:
            continue

        published_at = _parse_date_in_window(item.get("published_at"), now, cutoff)
        if published_at is None:
            continue

        publisher = resolve_publisher_meta(url, item.get("source_name", ""))
        if publisher is None:
            continue

        description = str(item.get("description") or "").strip()[:1200]
        if not is_civil_aviation_item(title, description, publisher):
            continue
        seen_urls.add(url)
        seen_titles.add(title_key)
        articles.append(
            _build_article(
                title,
                url,
                description,
                publisher,
                published_at,
                now,
                classify_topics_fn=classify_topics_fn,
                headline_only=publisher["source_type"] == "mainstream",
            )
        )
    return articles


def collect(api_key, now, cutoff, post=None, classify_topics_fn=None, include_rss=None):
    """Collect recent benchmark, wire, and blocked official airline/OEM reports via Google News RSS + Gemini Search Grounding.

    Never raises: returns (articles, report_dict).
    """
    if not api_key and post is None and not include_rss:
        return [], {"status": "not_configured", "error": "GEMINI_API_KEY is not configured", "articles": 0}

    use_rss = (post is None) if include_rss is None else bool(include_rss)
    rss_articles = []
    errors = []

    if use_rss:
        try:
            rss_articles.extend(collect_strategic_publications(now, cutoff, classify_topics_fn=classify_topics_fn))
            rss_articles.extend(collect_google_news_rss(now, cutoff, classify_topics_fn=classify_topics_fn))
            corroborate_thin_articles(rss_articles, classify_topics_fn=classify_topics_fn)
        except Exception as exc:
            errors.append(type(exc).__name__)

    thin_seeds = [article for article in rss_articles if len(str(article.get("description") or "")) < 60][:12]
    grounded_articles = []

    if api_key or post is not None:
        sender = post or (lambda: post_search_query(api_key, now, cutoff, seed_articles=thin_seeds))
        try:
            response = sender()
            apply_search_enrichment(response, thin_seeds, classify_topics_fn=classify_topics_fn)
            grounded_articles.extend(parse_search_response(response, now, cutoff, classify_topics_fn=classify_topics_fn))
        except urllib.error.HTTPError as exc:
            errors.append(f"HTTPError {exc.code}")
        except Exception as exc:
            errors.append(type(exc).__name__)

    deduped = []
    seen_keys = set()
    for article in rss_articles + grounded_articles:
        key = (article["source"].lower(), article["title"].lower()[:60])
        if key in seen_keys or article["link"] in seen_keys:
            continue
        seen_keys.add(key)
        seen_keys.add(article["link"])
        deduped.append(article)

    if not deduped and errors:
        return [], {"status": "error", "error": "; ".join(errors), "articles": 0}
    return deduped, {"status": "active", "error": "", "articles": len(deduped)}
