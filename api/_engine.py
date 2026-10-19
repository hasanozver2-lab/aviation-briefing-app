"""
Aviation Briefing Engine
Havacılık haberlerini RSS kaynaklarından toplar, Gemini 2.5 Flash ile analiz eder
ve executive brifing JSON çıktısını üretir.
"""

import os
import sys
import re
import json
import hashlib
import ssl
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

try:
    from . import source_registry
    from . import briefing_store
    from . import market_data
    from . import entities
    from . import story_lifecycle
    from . import language
    from . import feed_discovery
    from . import feed_sources
    from . import alert_feeds
    from . import benchmark_search
    from . import safety_context
    from . import source_catalog
    from .urls import canonicalize_url
except ImportError:
    import source_registry
    import briefing_store
    import market_data
    import entities
    import story_lifecycle
    import language
    import feed_discovery
    import feed_sources
    import alert_feeds
    import benchmark_search
    import safety_context
    import source_catalog
    from urls import canonicalize_url

# Windows cp1254 encoding fix
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Konfigürasyon ve Yollar
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
ENV_FILE = ROOT_DIR / ".env"
PIPELINE_CONFIG_PATH = BASE_DIR / "config" / "pipeline.json"
VALID_MODES = {"daily", "hourly"}
SOURCE_POLICY_VERSION = "airline-only-v6"
RSS_FETCH_TIMEOUT_SECONDS = 10
HTML_FETCH_TIMEOUT_SECONDS = 3
HTML_DETAIL_DATE_TIMEOUT_SECONDS = 4
MAX_HTML_DETAIL_DATE_REQUESTS = 3
SOURCE_FETCH_WORKERS = 8
SOURCE_TYPES = {
    "mainstream",
    "trade_media",
    "airline_ir",
    "airline_newsroom",
    "official_social",
    "regulator",
}
SECTION_ORDER = [
    "Turkey / THY and Turkish aviation",
    "European and other global airlines",
    "Route news",
    "Other areas",
]


def load_description_limit():
    """Characters of article description sent to the model; tunable without a code change."""
    config = json.loads(PIPELINE_CONFIG_PATH.read_text(encoding="utf-8"))
    limit = config["llm_description_max_chars"]
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError("llm_description_max_chars must be a positive integer")
    return limit


def validate_mode(mode):
    """Only accept modes backed by an isolated cache and prompt contract."""
    if mode not in VALID_MODES:
        raise ValueError("mode must be either 'daily' or 'hourly'")
    return mode


def utc_now():
    return datetime.now(timezone.utc)

def get_cache_path(filename):
    """Bulut/Serverless ortamlarinda /tmp dizinini, yerelde proje dizinini kullanir."""
    local_path = BASE_DIR / filename
    is_serverless = os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if is_serverless:
        tmp_path = Path("/tmp") / filename
        if not tmp_path.exists() and local_path.exists():
            try:
                tmp_path.write_bytes(local_path.read_bytes())
            except OSError:
                pass
        return tmp_path
    return local_path

CACHE_FILE_DAILY = get_cache_path("briefing_cache_daily.json")
CACHE_FILE_HOURLY = get_cache_path("briefing_cache_hourly.json")

def load_env():
    """DEV kökündeki .env dosyasından anahtarları yükler."""
    env = {}
    if ENV_FILE.exists():
        try:
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
        except Exception:
            pass
    return env

ENV = load_env()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or ENV.get("GEMINI_API_KEY", "")

# Genel medya akışlarında yalnızca havayolu/havacılık bağlamı olan başlıkları
# kabul ederiz. Resmi havayolu kanalları ise kaynak doğrulaması sayesinde
# başlıkta "airline" kelimesi geçmese bile (ör. finansal sonuç duyurusu)
# kabul edilebilir.
AIRLINE_RELEVANCE_TERMS = (
    "airline", "airlines", "airways", "carrier", "aviation", "havayolu",
    "havacılık", "uçuş", "flight", "route", "rota", "fleet", "filo",
    "aircraft", "uçak", "passenger", "yolcu", "cargo", "kargo", "airport",
    "havalimanı", "airspace", "hava sahası", "runway", "pist", "slot",
    "capacity", "kapasite", "traffic", "load factor", "yield", "fare",
    "revenue", "earnings", "profit", "order", "delivery", "teslimat",
    "grounded", "maintenance", "bakım", "pilot", "crew", "strike", "grev",
    "schedule", "tarife", "codeshare", "alliance", "ittifak", "merger",
    "acquisition", "birleşme", "satın alma", "bankruptcy", "iflas", "faa",
    "easa", "iata", "icao", "jet fuel", "jet yakıt", "saf", "baggage",
    "bagaj", "delay", "gecikme", "cancellation", "iptal", "diversion",
    "safety", "emniyet", "security", "güvenlik", "a320", "a321", "a330",
    "a350", "a380", "737", "747", "767", "777", "787", "e190", "embraer",
    "airbus", "boeing", "ancillary", "unbundling", "ffp", "megahubs",
    "otp", "mct", "cask", "rask", "aog", "wet-lease", "acmi", "gtf",
    "a321xlr", "cirium", "oag", "capa", "ideaworks", "ch-aviation",
    "eurocontrol", "aci world",
)

TOPIC_TERMS = {
    "airline_operations": ("flight", "uçuş", "schedule", "tarife", "delay", "gecikme", "cancellation", "iptal", "crew", "pilot", "bakım", "maintenance", "otp", "aog", "utilization"),
    "route_network": ("route", "rota", "destination", "uçuş ağı", "hub", "slot", "codeshare", "alliance", "ittifak", "megahubs", "mct", "connecting bank", "hub-bypass"),
    "fleet": ("fleet", "filo", "aircraft", "uçak", "a320", "a321", "a321xlr", "a330", "a350", "a380", "737", "747", "767", "777", "787", "e190", "airbus", "boeing", "embraer", "gtf", "leap", "wet-lease", "acmi"),
    "orders_deliveries": ("order", "sipariş", "delivery", "teslimat", "backlog", "purchase", "satın"),
    "finance_investor": ("earnings", "revenue", "gelir", "profit", "kâr", "loss", "zarar", "investor", "yatırımcı", "results", "sonuç", "dividend", "temettü", "ancillary", "unbundling", "ffp", "frequent-flier", "frequent flyer", "loyalty", "cask", "rask"),
    "regulation_safety": ("faa", "easa", "iata", "icao", "safety", "emniyet", "security", "güvenlik", "regulation", "düzenleme", "incident", "kaza", "eurocontrol"),
    "airports_airspace": ("airport", "havalimanı", "airspace", "hava sahası", "runway", "pist", "terminal", "atc", "air traffic", "aci world"),
    "fuel_sustainability": ("jet fuel", "jet yakıt", "saf", "sustainable aviation", "sürdürülebilir", "emissions", "karbon", "crack spread"),
    "labor": ("pilot", "crew", "çalışan", "işçi", "union", "sendika", "strike", "grev", "job", "istihdam"),
    "partnerships_ma": ("partnership", "ortaklık", "codeshare", "alliance", "merger", "birleşme", "acquisition", "satın alma", "stake", "hisse"),
}


def _env_value(name):
    """Read a deployment variable, falling back to the shared local .env."""
    return os.environ.get(name) or ENV.get(name, "")


def _source_record(name, url, category_hint, source_type="trade_media", **metadata):
    return {
        "category_hint": category_hint,
        "name": name,
        "url": url.strip() if isinstance(url, str) else "",
        "source_type": source_type if source_type in SOURCE_TYPES else "trade_media",
        "official": source_type in {"airline_ir", "airline_newsroom", "official_social"},
        **metadata,
    }


def _html_attribute(attributes, name):
    match = re.search(rf"\b{name}\s*=\s*['\"]([^'\"]+)['\"]", attributes, flags=re.IGNORECASE)
    return unescape(match.group(1)).strip() if match else ""


def _html_text(value):
    return clean_html(unescape(re.sub(r"<script\b.*?</script\s*>", " ", value, flags=re.IGNORECASE | re.DOTALL)))


def _extract_html_date(value):
    text = _html_text(value)
    patterns = (
        r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return ""


def extract_html_entries(content, source):
    """Extract explicitly marked press cards from a static official page."""
    page = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else str(content)
    entries = []
    required_class = source.get("html_link_class", "")
    href_fragment = source.get("html_href_contains", "")
    date_context_chars = int(source.get("html_date_context_chars") or 0)
    for match in re.finditer(r"<a\b(?P<attributes>[^>]*)>(?P<body>.*?)</a\s*>", page, flags=re.IGNORECASE | re.DOTALL):
        attributes = match.group("attributes")
        body = match.group("body")
        classes = _html_attribute(attributes, "class")
        if required_class and required_class not in classes.split():
            continue
        href = _html_attribute(attributes, "href")
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        if href_fragment and href_fragment not in href:
            continue
        title = _html_attribute(attributes, "title")
        heading_match = re.search(r"<h[1-4]\b[^>]*>(.*?)</h[1-4]\s*>", body, flags=re.IGNORECASE | re.DOTALL)
        heading = _html_text(heading_match.group(1)) if heading_match else ""
        image_match = re.search(r"<img\b(?P<attributes>[^>]*)>", body, flags=re.IGNORECASE | re.DOTALL)
        image_alt = _html_attribute(image_match.group("attributes"), "alt") if image_match else ""
        title = title or heading or image_alt or _html_text(body)
        description = _html_text(body)
        if heading and description.startswith(heading):
            description = description[len(heading):].strip()
        if len(title) < 12:
            continue
        pub_date = _extract_html_date(body)
        if not pub_date and date_context_chars:
            context_start = max(0, match.start() - date_context_chars)
            context_end = min(len(page), match.end() + date_context_chars)
            pub_date = _extract_html_date(page[context_start:context_end])
        entries.append({
            "title": title,
            "link": urllib.parse.urljoin(source["url"], href),
            "description": description[:1200],
            "pub_date": pub_date,
        })
    return entries[:20]


def fetch_html_detail_date(url, headers, ctx):
    """Read a detail page's explicit modified/published date when available."""
    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, context=ctx, timeout=HTML_DETAIL_DATE_TIMEOUT_SECONDS) as response:
            content = response.read().decode("utf-8", errors="replace")
        patterns = (
            r"(?:Last Modified|Published|Publication Date)\s*:\s*([^<]{3,80})",
            r"property=['\"]article:published_time['\"][^>]+content=['\"]([^'\"]+)",
            r"datePublished\"\s*:\s*\"([^\"]+)\"",
            r"<time\b[^>]*datetime=['\"]([^'\"]+)['\"]",
        )
        for pattern in patterns:
            match = re.search(pattern, content, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip()
    except Exception:
        return ""
    return ""


def _configured_source_records():
    """Load licensed/API feeds without committing secrets or provider URLs."""
    records = []
    for env_name, display_name, source_type in (
        ("REUTERS_AVIATION_RSS_URL", "Reuters Aviation", "mainstream"),
        ("FT_AVIATION_RSS_URL", "Financial Times Aviation", "mainstream"),
        ("BLOOMBERG_AVIATION_RSS_URL", "Bloomberg Aviation", "mainstream"),
    ):
        url = _env_value(env_name)
        if url:
            records.append(_source_record(
                display_name,
                url,
                "European and other global airlines",
                source_type,
                license_required=True,
                active=False,
                region="Global",
                tier=3,
            ))

    # AIRLINE_BRIEFING_SOURCES_JSON; örnek biçim README'de açıklanmıştır.
    # Böylece yüzlerce resmi feed Vercel env üzerinden kod değişmeden eklenebilir.
    raw_registry = _env_value("AIRLINE_BRIEFING_SOURCES_JSON")
    if raw_registry:
        try:
            parsed_registry = json.loads(raw_registry)
        except (TypeError, json.JSONDecodeError) as exc:
            print(f"AIRLINE_BRIEFING_SOURCES_JSON okunamadı: {exc}")
            parsed_registry = []
        if isinstance(parsed_registry, list):
            for record in parsed_registry:
                if not isinstance(record, dict):
                    continue
                name = record.get("name")
                url = record.get("url")
                if not isinstance(name, str) or not isinstance(url, str) or not url.strip():
                    continue
                source_options = {
                    key: record.get(key)
                    for key in ("fetch_mode", "html_link_class", "html_href_contains", "endpoint_url")
                    if isinstance(record.get(key), str) and record.get(key)
                }
                if isinstance(record.get("html_date_context_chars"), int):
                    source_options["html_date_context_chars"] = record["html_date_context_chars"]
                for key in ("date_required", "resolve_detail_dates"):
                    if key in record:
                        source_options[key] = bool(record.get(key))
                records.append(_source_record(
                    name,
                    url,
                    str(record.get("category_hint") or "European and other global airlines"),
                    str(record.get("source_type") or "airline_newsroom"),
                    airline=str(record.get("airline") or ""),
                    airline_code=str(record.get("airline_code") or ""),
                    official=True,
                    license_required=bool(record.get("license_required", False)),
                    **source_options,
                ))
    return records


def normalize_article_text(*values):
    return " ".join(str(value or "") for value in values).casefold()


def classify_topics(text):
    normalized = normalize_article_text(text)
    return [topic for topic, terms in TOPIC_TERMS.items() if any(term in normalized for term in terms)]


def is_airline_relevant(title, description="", source=None):
    """Reject generic/non-airline stories before they reach the model."""
    source = source if isinstance(source, dict) else {}
    normalized = normalize_article_text(title, description)
    if source.get("official") and source.get("source_type") in {"airline_ir", "airline_newsroom"}:
        return True
    return any(term in normalized for term in AIRLINE_RELEVANCE_TERMS)

def get_builtin_source_records(max_hours=48):
    """Return source definitions before SQLite governance flags are applied."""
    sources = [
        # 1. Turkey / THY and Turkish aviation
        _source_record("HavaHaber", "https://havahaber.com/feed/", "Turkey / THY and Turkish aviation"),
        _source_record("Tolga Özbek Havacılık", "https://tolgaozbek.com/feed/", "Turkey / THY and Turkish aviation"),
        _source_record("Yahoo Finance (THY & Pegasus)", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=THYAO.IS,PGSUS.IS", "Turkey / THY and Turkish aviation", "mainstream"),
        # 2. European and other global airlines
        _source_record("Simple Flying", "https://simpleflying.com/feed/", "European and other global airlines"),
        _source_record("FlightGlobal", "https://www.flightglobal.com/rss", "European and other global airlines"),
        _source_record("AeroTime", "https://www.aerotime.aero/feed", "European and other global airlines"),
        _source_record("Aviation24", "https://www.aviation24.be/feed/", "European and other global airlines"),
        # 3. Route news & Fleet
        _source_record("AirDataNews", "https://www.airdatanews.com/feed/", "Route news"),
        _source_record("Flightradar24", "https://www.flightradar24.com/blog/feed/", "Route news"),
        # 4. Other areas (Market & Industry)
        _source_record("Yahoo Finance Aviation", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=LHA.DE,AF.PA,IAG.L,AAL,DAL,BA,AIR.PA", "Other areas", "mainstream"),
        # 5. Verified official airline newsroom / social feeds
        _source_record("Lufthansa Group Newsroom", "https://newsroom.lufthansagroup.com/feed/en", "European and other global airlines", "airline_newsroom", airline="Lufthansa Group", airline_code="LH"),
        _source_record("Delta News Hub", "https://news.delta.com/rss.xml", "European and other global airlines", "airline_newsroom", airline="Delta Air Lines", airline_code="DL"),
        _source_record("Turkish Airlines Blog", "https://blog.turkishairlines.com/en/feed/", "Turkey / THY and Turkish aviation", "official_social", airline="Turkish Airlines", airline_code="TK"),
        _source_record("Emirates Newsroom", "https://www.emirates.com/media-centre/feed/en-us", "European and other global airlines", "airline_newsroom", airline="Emirates", airline_code="EK"),
        _source_record("Qatar Airways Official Tumblr", "https://qatarairways.tumblr.com/rss", "European and other global airlines", "official_social", airline="Qatar Airways", airline_code="QR"),
        _source_record("Pegasus Press Room", "https://www.flypgs.com/en/press-room", "Turkey / THY and Turkish aviation", "airline_newsroom", airline="Pegasus Airlines", airline_code="PC", fetch_mode="html", html_link_class="press__link", date_required=True, resolve_detail_dates=True),
        # 6. Verified official sources for additional global carriers
        _source_record("American Airlines Newsroom", "https://news.aa.com/news/", "North American airlines", "airline_newsroom", airline="American Airlines", airline_code="AA", fetch_mode="html", html_href_contains="/news/", html_date_context_chars=1800, date_required=True, resolve_detail_dates=True),
        _source_record("United Airlines Newsroom", "https://newsroom.united.com/", "North American airlines", "airline_newsroom", airline="United Airlines", airline_code="UA", fetch_mode="html", html_href_contains="/news/", html_date_context_chars=1800, date_required=True, resolve_detail_dates=True),
        _source_record("Southwest Newsroom", "https://www.swamedia.com/news-and-stories/news-releases", "North American airlines", "airline_newsroom", airline="Southwest Airlines", airline_code="WN", fetch_mode="html", html_href_contains="/news-and-stories/", html_date_context_chars=1800, date_required=True, resolve_detail_dates=True),
        _source_record("Air France Press Releases", "https://corporate.airfrance.com/en/rss-subscription", "European and other global airlines", "airline_newsroom", airline="Air France", airline_code="AF"),
        _source_record("KLM Newsroom", "https://nieuws.klm.com/feed/en", "European and other global airlines", "airline_newsroom", airline="KLM", airline_code="KL"),
        _source_record("Air Canada News Releases", "https://www.aircanada.com/media/?h=1&t=news%20release", "North American airlines", "airline_newsroom", airline="Air Canada", airline_code="AC", fetch_mode="html", html_link_class="text_latestnews_more", html_date_context_chars=2200, date_required=True),
        _source_record("Ryanair Newsroom", "https://corporate.ryanair.com/media-centre/our-news/?market=ua", "European and other global airlines", "airline_newsroom", airline="Ryanair", airline_code="FR", fetch_mode="html", html_href_contains="/news/", html_date_context_chars=2400, date_required=True),
        _source_record("easyJet Media Centre", "https://www.easyjet.com/en/news/airline", "European and other global airlines", "airline_newsroom", airline="easyJet", airline_code="U2", fetch_mode="html", html_link_class="stories-card", date_required=True),
        _source_record("Qantas Newsroom", "https://www.qantasnewsroom.com.au/", "Asia-Pacific airlines", "airline_newsroom", airline="Qantas", airline_code="QF", fetch_mode="html", html_href_contains="qantasnewsroom.com.au", html_date_context_chars=2200, date_required=True, resolve_detail_dates=True),
        _source_record("Singapore Airlines Newsroom", "https://www.singaporeair.com/en_UK/au/corporate/newsroom/press-release/", "Asia-Pacific airlines", "airline_newsroom", airline="Singapore Airlines", airline_code="SQ", fetch_mode="html", html_href_contains="/corporate/newsroom/press-release/", html_date_context_chars=2200, date_required=True),
        _source_record("ANA Group Press Releases", "https://www.ana.co.jp/group/en/pr/", "Asia-Pacific airlines", "airline_newsroom", airline="ANA", airline_code="NH", fetch_mode="html", html_href_contains="/group/en/pr/", html_date_context_chars=2200, date_required=True),
        _source_record("Japan Airlines Press Releases", "https://press.jal.co.jp/en/", "Asia-Pacific airlines", "airline_newsroom", airline="Japan Airlines", airline_code="JL", fetch_mode="html", html_href_contains="/en/", html_date_context_chars=2200, date_required=True),
        _source_record("Cathay Pacific Newsroom", "https://news.cathaypacific.com/gb", "Asia-Pacific airlines", "airline_newsroom", airline="Cathay Pacific", airline_code="CX", fetch_mode="html", html_href_contains="/gb/", html_date_context_chars=2200, date_required=True, resolve_detail_dates=True),
        _source_record("Air India Newsroom", "https://www.airindia.com/in/en/newsroom/corporate/news-and-announcements.html", "Asia-Pacific airlines", "airline_newsroom", airline="Air India", airline_code="AI", fetch_mode="html", html_href_contains="/in/en/newsroom/", html_date_context_chars=2200, date_required=True, resolve_detail_dates=True),
        _source_record("Etihad Airways News", "https://www.etihad.com/en/news", "Middle East airlines", "airline_newsroom", airline="Etihad Airways", airline_code="EY", fetch_mode="html", html_href_contains="/en/news/", html_date_context_chars=2200, date_required=True, resolve_detail_dates=True),
        _source_record("IndiGo Press Releases", "https://www.goindigo.in/press-releases.html", "Asia-Pacific airlines", "airline_newsroom", airline="IndiGo", airline_code="6E", fetch_mode="html", html_href_contains="/press-releases/", html_date_context_chars=2200, date_required=True, resolve_detail_dates=True),
        _source_record("JetBlue Investor News", "https://ir.jetblue.com/news/", "North American airlines", "airline_ir", airline="JetBlue", airline_code="B6", fetch_mode="html", html_href_contains="/news/", html_date_context_chars=2200, date_required=True, resolve_detail_dates=True),
        _source_record("Copa Holdings News Releases", "https://ir.copaair.com/press-releases", "Latin American airlines", "airline_ir", airline="Copa Airlines", airline_code="CM", fetch_mode="html", html_href_contains="/news-releases/", html_date_context_chars=2200, date_required=True, resolve_detail_dates=True),
        _source_record("LATAM Investor Releases", "https://ir.latam.com/news/press-releases/", "Latin American airlines", "airline_ir", airline="LATAM Airlines", airline_code="LA", fetch_mode="html", html_href_contains="/news/press-releases/", html_date_context_chars=2200, date_required=True, resolve_detail_dates=True),
        _source_record("Alaska Airlines Newsroom", "https://news.alaskaair.com/press-center/latest-news/category/releases/", "North American airlines", "airline_newsroom", airline="Alaska Airlines", airline_code="AS", fetch_mode="html", html_href_contains="news.alaskaair.com/", html_date_context_chars=2200, date_required=True, resolve_detail_dates=True),
    ]
    sources.extend(_configured_source_records())
    return [source for source in sources if source.get("url")]


def get_rss_sources(max_hours=48):
    """Return only the active feeds, decorated with source-governance metadata and the catalog's timeout and mode."""
    sources = source_registry.load_active_sources(get_builtin_source_records(max_hours))
    rows = source_catalog.read_rows()
    preferred = feed_sources.catalog_preferred_names(rows, feed_sources.load_discovered())
    sources = [source for source in sources if source.get("name") not in preferred]
    catalog = {row["name"]: row for row in rows}
    for source in sources:
        row = catalog.get(source.get("name"))
        if row:
            source["timeout_s"] = int(row["timeout_s"])
            source["mode"] = row["mode"]
    return sources

def clean_html(raw_html):
    """HTML etiketlerini temizler."""
    if not raw_html:
        return ""
    clean = re.sub(r'<.*?>', ' ', raw_html)
    # Feeds escape punctuation as numeric entities (&#8217;); left raw they show up in the text and as fake numbers.
    return " ".join(unescape(clean).split()).strip()


def _local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element, names):
    wanted = set(names)
    for child in list(element):
        if _local_name(child.tag) not in wanted:
            continue
        value = "".join(child.itertext()).strip()
        if value:
            return value
    return ""


def parse_feed_entries(content):
    """Parse both RSS 2.0 and Atom without an additional dependency."""
    root = ET.fromstring(content)
    root_name = _local_name(root.tag)
    if root_name == "rss":
        channel = next((child for child in list(root) if _local_name(child.tag) == "channel"), None)
        return [child for child in list(channel) if _local_name(child.tag) == "item"] if channel is not None else []
    if root_name == "feed":
        return [child for child in list(root) if _local_name(child.tag) == "entry"]
    return []


def entry_values(entry, include_description=True):
    title = _child_text(entry, {"title"})
    description = _child_text(entry, {"description", "summary", "content"}) if include_description else ""
    link = _child_text(entry, {"link"})
    if not link:
        for child in list(entry):
            if _local_name(child.tag) == "link" and child.attrib.get("href"):
                link = child.attrib["href"].strip()
                break
    pub_date = _child_text(entry, {"pubdate", "published", "updated", "date", "issued"})
    return title, link, clean_html(description) if include_description else "", pub_date


def parse_published_datetime(value):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
            for date_format in ("%d %B %Y", "%B %d, %Y", "%d %b %Y", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(value.strip(), date_format)
                    break
                except ValueError:
                    continue
            if parsed is None:
                for date_format in ("%d %B", "%d %b"):
                    try:
                        parsed = datetime.strptime(value.strip(), date_format).replace(year=utc_now().year)
                        break
                    except ValueError:
                        continue
            if parsed is None:
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def describe_fetch_error(exc):
    """Error name for the run log; an HTTP failure carries its status code (403 = blocked, 404 = moved) so it can be told apart."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTPError {exc.code}"
    reason = getattr(exc, "reason", None)
    return f"{type(exc).__name__} ({type(reason).__name__})" if reason is not None and not isinstance(reason, str) else type(exc).__name__


def _fetch_source_articles(source, cutoff, headers):
    """Fetch one source independently so a slow site cannot block the briefing."""
    source_name = source.get("name", "Unknown source")
    is_html_source = source.get("fetch_mode") == "html"
    is_paid_source = source.get("license_status") == "paid" or source.get("license_required", False)
    timeout = source.get("timeout_s") or (HTML_FETCH_TIMEOUT_SECONDS if is_html_source else RSS_FETCH_TIMEOUT_SECONDS)
    feed_only = source.get("mode") == feed_sources.MODE_FEED_ONLY

    try:
        if is_paid_source and is_html_source:
            return [], "PaidSourceNeedsLicensedFeed"
        ctx = ssl.create_default_context()
        request = urllib.request.Request(source["url"], headers=headers)
        with urllib.request.urlopen(request, context=ctx, timeout=timeout) as response:
            content = response.read()

        entries = extract_html_entries(content, source) if is_html_source else parse_feed_entries(content)
        detail_date_requests = 0
        articles = []
        for item in entries[:20]:
            if is_html_source:
                title = item.get("title", "")
                link = item.get("link", "")
                description = ""
                pub_date = item.get("pub_date", "")
            else:
                title, link, description, pub_date = entry_values(item, include_description=not is_paid_source)

            if not title or not link:
                continue
            if not is_airline_relevant(title, description, source):
                continue

            can_resolve_date = (
                not pub_date
                and source.get("resolve_detail_dates")
                and detail_date_requests < MAX_HTML_DETAIL_DATE_REQUESTS
            )
            if can_resolve_date:
                pub_date = fetch_html_detail_date(link, headers, ctx)
                detail_date_requests += 1
            if source.get("date_required") and not pub_date:
                continue

            pub_ts = time.time()
            pub_str = ""
            if pub_date:
                published_at = parse_published_datetime(pub_date)
                if published_at:
                    if published_at < cutoff:
                        continue
                    pub_ts = published_at.timestamp()
                    pub_str = published_at.strftime("%d %b %H:%M")

            article_source_name = source_name
            if not is_html_source and " - " in title:
                title, article_source_name = (part.strip() for part in title.rsplit(" - ", 1))

            if feed_only:
                description = description[:feed_sources.FEED_ONLY_SUMMARY_CHARS]
            article = {
                "title": title,
                "link": link,
                "description": description,
                "source": article_source_name,
                "language": language.article_language(source_name, f"{title} {description}"),
                "category_hint": source["category_hint"],
                "source_type": source.get("source_type", "trade_media"),
                "official": bool(source.get("official", False)),
                "airline": source.get("airline", ""),
                "airline_code": source.get("airline_code", ""),
                "license_required": bool(source.get("license_required", False)),
                "license_status": source.get("license_status", "public"),
                "source_id": source.get("source_id"),
                "region": source.get("region", "Global"),
                "tier": source.get("tier"),
                "reliability_weight": source.get("reliability_weight"),
                "topics": classify_topics(f"{title} {description}"),
                "pub_date": pub_str,
                "timestamp": pub_ts,
            }
            if feed_only:
                article["basis"] = feed_sources.BASIS_HEADLINE_ONLY
            articles.append(article)
        return articles, ""
    except Exception as exc:
        return [], describe_fetch_error(exc)


def _read_catalog_feeds(cutoff, report, entity_index_factory=None, recovered=None):
    """Catalog sources read through their discovered feeds: hosts in parallel, the sources of one host strictly in turn."""
    rows = source_catalog.read_rows()
    discovered = feed_sources.load_discovered()
    preferred = feed_sources.catalog_preferred_names(rows, discovered)
    handled = ({source["name"] for source in get_builtin_source_records()} - preferred) | {alert_feeds.SOURCE_NAME}    # alerts have their own reader
    recovered = recovered or {}
    sources = feed_sources.catalog_feed_sources(rows, handled)
    for row in rows:
        if row["name"] in handled or row["status"] == source_catalog.STATUS_ACTIVE:
            continue
        if row["name"] in recovered:      # blocked in the catalog, but this week's retry (status.json) found valid content again
            record = feed_sources.source_record(row)
            record["status"] = source_catalog.STATUS_ACTIVE
            sources.append(record)
            discovered[record["slug"]] = {"feed_url": recovered[row["name"]]["feed_url"], "method": recovered[row["name"]]["method"]}
        else:
            report[row["name"]] = {"status": row["status"], "error": row["reason"], "articles": 0}
    if not sources:
        return []
    now = utc_now()
    groups = feed_sources.group_by_host(sources)

    def read_host(host_sources):
        fetcher = feed_discovery.PoliteFetcher()
        collected = []
        for source in host_sources:
            fetcher.timeout = source["timeout_s"]
            try:
                items, source_report = feed_sources.read_source(source, discovered, fetcher, now, cutoff)
            except Exception as exc:      # one source must never take the run down
                items, source_report = [], {"status": "error", "error": describe_fetch_error(exc), "articles": 0}
            collected.append((source, items, source_report))
        return collected

    articles = []
    with ThreadPoolExecutor(max_workers=min(SOURCE_FETCH_WORKERS, len(groups)), thread_name_prefix="briefing-feed-host") as executor:
        results = [result for host_result in executor.map(read_host, groups.values()) for result in host_result]
    needs_filter = [(source, items) for source, items, _ in results if source["aviation_filter"]]
    index = entity_index_factory() if (entity_index_factory and any(items for _, items in needs_filter)) else None
    for source, items, source_report in results:
        if source["aviation_filter"] and items:
            items, dropped = feed_sources.filter_for_aviation(items, index)
            items = items[:feed_sources.MAX_ITEMS_PER_SOURCE]
            source_report["filtered_out"] = dropped
            source_report["articles"] = len(items)
        report[source["name"]] = source_report
        if source_report["status"] != "active" or source_report.get("error"):
            print(f"[{source['name']}] Kaynak atlandı ({source_report['status']}: {source_report['error']}).")
        articles.extend(items)
    return articles


def fetch_rss_items(max_hours=48, report=None, recovered=None):
    """Fetch recent airline-relevant entries without serial source delays.

    `report`, when given, is filled with one entry per source: status, error, articles (and articles_24h at the end).
    """
    report = report if report is not None else {}
    cutoff = utc_now() - timedelta(hours=max_hours)
    # One self-identifying User-Agent for every source; robots.txt is obeyed and the sources of one host
    # are read one after the other, different hosts in parallel.
    headers = {"User-Agent": feed_discovery.USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/html;q=0.8, */*;q=0.5"}
    sources = get_rss_sources(max_hours)
    if recovered:
        known = {source.get("name") for source in sources}
        catalog = {row["name"]: row for row in source_catalog.read_rows()}
        for source in get_builtin_source_records(max_hours):
            if source["name"] in recovered and source["name"] not in known and source["name"] in catalog:
                source["timeout_s"], source["mode"] = int(catalog[source["name"]]["timeout_s"]), catalog[source["name"]]["mode"]
                sources.append(source)
    hosts = {}
    for source in sources:
        hosts.setdefault(source_catalog.registrable_key(source.get("url", "")), []).append(source)

    def read_host(host_sources):
        fetcher = feed_discovery.PoliteFetcher()
        results = []
        for number, source in enumerate(host_sources):
            if number:
                time.sleep(feed_discovery.SAME_HOST_GAP_SECONDS)
            try:
                if not fetcher.allowed(source["url"]):
                    results.append((source, [], "robots.txt disallows this address", "excluded_policy"))
                    continue
                source_articles, error_name = _fetch_source_articles(source, cutoff, headers)
            except Exception as exc:
                source_articles, error_name = [], describe_fetch_error(exc)
            results.append((source, source_articles, error_name, "active"))
        return results

    articles = []
    worker_count = max(1, min(SOURCE_FETCH_WORKERS, len(hosts)))
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="briefing-feed") as executor:
        for host_results in executor.map(read_host, hosts.values()):
            for source, source_articles, error_name, status in host_results:
                articles.extend(source_articles)
                report[source.get("name", "Unknown source")] = {"status": status, "error": error_name, "articles": len(source_articles)}
                if error_name:
                    print(f"[{source.get('name', 'Unknown source')}] Kaynak atlandı ({error_name}).")

    articles.extend(_read_catalog_feeds(cutoff, report, entity_index_factory=entities.EntityIndex.from_csv, recovered=recovered))
    alert_articles, report[alert_feeds.SOURCE_NAME] = alert_feeds.collect(_env_value(alert_feeds.ENV_NAME), utc_now(), cutoff, entity_index_factory=entities.EntityIndex.from_csv)
    articles.extend(alert_articles)
    benchmark_articles, benchmark_report = benchmark_search.collect(
        "",  # Publisher-written reports require no model call or API key.
        utc_now(),
        cutoff,
        classify_topics_fn=classify_topics,
        deep_scan=story_lifecycle.is_morning_deep_window(utc_now()),
    )
    if benchmark_report:
        report[benchmark_search.SOURCE_NAME] = benchmark_report
    articles.extend(benchmark_articles)
    articles.sort(key=lambda article: article.get("timestamp", 0), reverse=True)
    seen_links = set()
    unique_articles = []
    for article in articles:
        canonical_link = canonicalize_url(article["link"])
        if not canonical_link or canonical_link in seen_links:
            continue
        seen_links.add(canonical_link)
        unique_articles.append(article)
    day_ago = (utc_now() - timedelta(hours=24)).timestamp()
    for article in unique_articles:
        report_key = (
            alert_feeds.SOURCE_NAME
            if article.get("via_alert")
            else benchmark_search.SOURCE_NAME
            if article.get("via_benchmark_search")
            else article["source"]
        )
        entry = report.setdefault(report_key, {"status": "active", "error": "", "articles": 0})
        entry["articles_24h"] = entry.get("articles_24h", 0) + (1 if article.get("timestamp", 0) >= day_ago else 0)
    return unique_articles

def build_compact_articles(articles, description_limit=None):
    """Only title, source, time, a bounded description and deterministic labels go to the model."""
    # Read at use time so the read-only API never depends on pipeline.json at import.
    limit = description_limit or load_description_limit()
    return [
        {
            "title": a["title"],
            "source": a["source"],
            "source_type": a.get("source_type", "trade_media"),
            "official": bool(a.get("official", False)),
            "airline": a.get("airline", ""),
            "topics": a.get("topics", []),
            "event_type": a.get("event_type"),
            "entities": entities.compact_codes(a.get("entities") or entities.empty_entities()),
            "published_at": a.get("pub_date", ""),
            "category_hint": a.get("category_hint", ""),
            "description": a["description"][:limit] if a.get("description") else "",
            "link": a["link"]
        }
        for a in articles
    ]


def deterministic_fields(article):
    """Rule-based labels computed before the model runs; the model never writes these."""
    article = article if isinstance(article, dict) else {}
    return {
        "event_type": article.get("event_type"),
        "entities": article.get("entities") or entities.empty_entities(),
        "region_section": article.get("region_section", ""),
        "secondary_tags": article.get("secondary_tags") or [],
        "is_strategic_report": story_lifecycle.is_strategic_report(article),
    }


def generate_briefing_with_gemini(articles, mode="daily"):
    """Gemini 2.5 Flash ile haberleri prompt kurallarına göre analiz eder."""
    mode = validate_mode(mode)
    if not GEMINI_API_KEY:
        print("Uyarı: GEMINI_API_KEY bulunamadı; yalnız kaynak özetleri gösterilecek.")
        return fallback_briefing(
            articles,
            mode,
            "AI analysis is unavailable because the API key is not configured.",
        )

    sample_articles = articles[:12]
    compact_articles = build_compact_articles(sample_articles)
    if not compact_articles:
        return fallback_briefing([], mode)

    now = utc_now()
    today_str = now.strftime('%d %B %Y')

    prompt_mode_instructions = f"""
Mode: DAILY (Last 48 Hours)
- Today is {today_str}.
- STRONGLY prioritize the freshest breaking news published today and in the last 24-48 hours.
- Discard any outdated, historical or stale news items.
- Detailed Analysis: 4 to 6 short, punchy bullet points per story.
- Include data points, strategic implications, capacity / demand / revenue effects, competition effects, and operational outcomes whenever possible.
- Explicitly cover the effect on Turkish Airlines (THY) within analysis bullets where relevant.
""" if mode == "daily" else f"""
Mode: HOURLY (Last 1-2 Hours)
- Today is {today_str}.
- Shorter analysis: 2 to 3 short bullets under Detailed Analysis.
- Include only genuinely new, breaking developments from the current hourly window.
"""

    system_prompt = f"""
You are an expert aviation industry analyst creating an essential daily briefing for airline employees and aviation professionals (pilots, cabin managers, dispatchers, network planners, revenue managers, engineers, and aviation specialists).
Your task is to take the provided verified news items and compile an up-to-the-minute Aviation Intelligence Briefing adhering strictly to institutional analysis standards.
Today's date is {today_str}. All analysis must reflect the freshest verified information.
STRICT SCOPE: Include only airline, air transport, airport/airspace, aircraft fleet, route network, airline finance/investor, airline labor, safety/regulation, fuel/sustainability, or airline partnership/M&A developments. Exclude unrelated general business, politics, defense, space, technology, or tourism stories even when they come from a mainstream source. Preserve the supplied official/mainstream source metadata and never invent an original source.

Required Sections (Strict Order):
1. `Turkey / THY and Turkish aviation`
2. `European and other global airlines`
3. `Route news`
4. `Other areas`

Each Story Block Structure:
- `id`: unique slug e.g. "story-1", "story-2"
- `section`: One of the 4 exact section names above.
- `headline`: One concise, impactful executive headline.
- `published_at`: Publication timestamp from the supplied source item.
- `lead`: 1 short executive lead paragraph.
- `detailed_analysis`: Array of strings (4-6 bullets for daily, 2-3 for hourly). Include strategy, capacity, demand, revenue, fleet, competition.
- `data_points`: Array of strings with concrete numerical data (e.g. capacity, frequency, revenue, passengers, ASK, RPK, load factor, delivery count). Leave EMPTY array if no concrete numerical data exists in the story.
- `strategic_impact`: High-level executive strategic and commercial assessment (revenue, operational costs, network implications, capacity shifts, or fleet modernization).
- `market_exposure`: Array of objects detailing affected carriers or key market stakeholders with their impact tag, e.g.:
  [
    {{"carrier": "Turkish Airlines (THY)", "impact": "Positive", "details": "Benefits from enhanced hub connectivity and transfer traffic."}},
    {{"carrier": "European Legacy Carriers", "impact": "Competitive Headwind", "details": "Increased transfer pressure on long-haul routes."}}
  ]
- `thy_impact_assessment`: Assessment from Turkish Airlines' (THY) perspective (impact on revenue, cost, competition, route network, fleet, demand, operations, or brand). State honestly if direct impact is weak.
- `why_it_matters`: Single consequence-focused sentence discussing impact only through market impact, security risk, financial impact, or operational change.
- `original_source`: {{"title": "Article Title", "source_name": "publisher name", "url": "direct real url"}}
- `related_news`: Array of strings (optional, can be empty).
(Do NOT include any numerical risk score).

{prompt_mode_instructions}

Return pure JSON matching this schema:
{{
  "mode": "{mode}",
  "date_str": "{now.strftime('%d %B %Y')}",
  "time_str": "{now.strftime('%H:%M UTC')}",
  "heading": "{'Aviation Briefing | ' + now.strftime('%d %B %Y') if mode == 'daily' else 'Aviation Update | ' + now.strftime('%d %B %Y %H:%M UTC')}",
  "intro_sentence": "{'Below is a summary of the most important verified aviation developments from the last 48 hours.' if mode == 'daily' else 'Below is a summary of the most important newly verified or strongly supported aviation developments for the current hourly window.'}",
  "stories": [
    ...
  ]
}}
Ensure stories are grouped by the 4 required sections in order. Select 6 to 10 of the most strategic stories.
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": system_prompt},
                    {"text": "RAW NEWS ARTICLES TO ANALYZE:\n" + json.dumps(compact_articles, ensure_ascii=False, indent=2)}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }

    ctx = ssl.create_default_context()

    try:
        data = None
        last_err = None
        for model_name in (
            "gemini-3.5-flash",
            "gemini-3-flash-preview",
            "gemini-3.7-flash",
            "gemini-3.8-flash",
            "gemini-3.5-flash-lite",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
        ):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": GEMINI_API_KEY,
                },
            )
            try:
                with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    break
            except urllib.error.HTTPError as exc:
                last_err = exc
                if exc.code in {404, 429, 500, 503}:
                    continue
                raise
        if data is None and last_err is not None:
            raise last_err
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        briefing = json.loads(content)
        article_metadata = {
            canonicalize_url(article.get("link")): article
            for article in articles
            if canonicalize_url(article.get("link"))
        }
        normalized = normalize_generated_briefing(briefing, mode, article_metadata)
        if not normalized["stories"] and articles:
            return fallback_briefing(
                articles,
                mode,
                "AI output did not reference the approved source items; source headlines are shown instead.",
            )
        return normalized
    except Exception as e:
        print(f"Gemini API hatası ({e}); yalnız kaynak özetleri gösterilecek.")
        return fallback_briefing(
            articles,
            mode,
            "AI analysis could not be generated; source summaries are shown instead.",
        )

def safe_source_url(value):
    if not isinstance(value, str):
        return ""
    parsed = urllib.parse.urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return value.strip()


def stable_story_id(source_url, headline, fallback_index):
    """Keep the same story addressable across runs, modes and days (hash of the canonical source URL)."""
    return story_lifecycle.stable_story_id(source_url, headline or f"story-{fallback_index}")


def text_list(value):
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def normalize_generated_briefing(briefing, mode, article_metadata=None):
    """Keep model output within the public JSON contract."""
    if not isinstance(briefing, dict) or not isinstance(briefing.get("stories"), list):
        raise ValueError("Gemini returned an invalid briefing payload")

    stories = []
    for index, raw_story in enumerate(briefing["stories"][:10], start=1):
        if not isinstance(raw_story, dict):
            continue
        source = raw_story.get("original_source")
        source = source if isinstance(source, dict) else {}
        section = raw_story.get("section")
        if section not in SECTION_ORDER:
            section = "Other areas"

        exposure = []
        raw_exposures = raw_story.get("market_exposure", [])
        if isinstance(raw_exposures, list):
            for raw_exposure in raw_exposures:
                if not isinstance(raw_exposure, dict):
                    continue
                exposure.append({
                    "carrier": str(raw_exposure.get("carrier", "Stakeholder")),
                    "impact": str(raw_exposure.get("impact", "Neutral")),
                    "details": str(raw_exposure.get("details", "")),
                })

        source_url = safe_source_url(source.get("url"))
        source_article = (article_metadata or {}).get(canonicalize_url(source_url), {})
        if article_metadata is not None and (not source_url or not source_article):
            # Model output must point to an item we actually fetched; this
            # prevents unrelated/hallucinated stories from entering the feed.
            continue
        normalized_source_type = source_article.get("source_type") or source.get("source_type") or "trade_media"
        if normalized_source_type not in SOURCE_TYPES:
            normalized_source_type = "trade_media"
        stories.append({
            "id": stable_story_id(source.get("url"), raw_story.get("headline"), index),
            "section": section,
            "headline": str(raw_story.get("headline", "Untitled aviation update")),
            "published_at": str(raw_story.get("published_at", "")),
            "lead": str(raw_story.get("lead", "")),
            "detailed_analysis": text_list(raw_story.get("detailed_analysis")),
            "data_points": text_list(raw_story.get("data_points")),
            "strategic_impact": str(raw_story.get("strategic_impact", "")),
            "market_exposure": exposure,
            **deterministic_fields(source_article),
            "thy_impact_assessment": str(raw_story.get("thy_impact_assessment", "")),
            "why_it_matters": str(raw_story.get("why_it_matters", "")),
            "original_source": {
                "title": str(source.get("title", "Read full article")),
                "source_name": str(source.get("source_name", "")),
                "url": source_url,
                "source_type": normalized_source_type,
                "official": bool(source_article.get("official", source.get("official", False))),
                "airline": str(source_article.get("airline", source.get("airline", ""))),
                "topics": source_article.get("topics", source.get("topics", [])),
                "license_required": bool(source_article.get("license_required", source.get("license_required", False))),
                "license_status": str(source_article.get("license_status", source.get("license_status", "public"))),
                "region": str(source_article.get("region", source.get("region", "Global"))),
                "tier": source_article.get("tier", source.get("tier")),
                "reliability_weight": source_article.get("reliability_weight", source.get("reliability_weight")),
            },
            "related_news": text_list(raw_story.get("related_news")),
        })

    return build_briefing_payload(mode, stories, status="ok")


def build_briefing_payload(mode, stories, status, warning=""):
    now = utc_now()
    date_str = now.strftime("%d %B %Y")
    time_str = now.strftime("%H:%M UTC")
    is_verified_daily = status == "ok" and mode == "daily"
    intro_sentence = (
        "Below is a summary of the most important verified aviation developments from the last 48 hours."
        if is_verified_daily
        else "Below is the latest available aviation source feed."
    )
    return {
        "mode": mode,
        "source_policy": SOURCE_POLICY_VERSION,
        "date_str": date_str,
        "time_str": time_str,
        "heading": f"Aviation Briefing | {date_str}" if mode == "daily" else f"Aviation Update | {date_str} {time_str}",
        "intro_sentence": intro_sentence,
        "stories": stories,
        "status": status,
        "warning": warning,
        "generated_at": now.isoformat(),
    }


def build_candidate_story(article, index=1):
    """A story made only of source data; its narrative stays "pending" until the LLM step fills it."""
    section = article.get("category_hint")
    if section not in SECTION_ORDER:
        section = "Other areas"
    return {
        "id": stable_story_id(article.get("link"), article.get("title"), index),
        "section": section,
        "headline": str(article.get("title", "Untitled aviation update")),
        "published_at": str(article.get("pub_date", "")),
        # A headline-only source's summary is used once to write the model's own summary; it is never published as the lead.
        "lead": "" if article.get("basis") else str(article.get("description", ""))[:400],
        "source_description": str(article.get("description", "")),
        "detailed_analysis": [],
        "data_points": [],
        "strategic_impact": "",
        "market_exposure": [],
        **deterministic_fields(article),
        "thy_impact_assessment": "",
        "why_it_matters": "",
        "original_source": {
            "title": str(article.get("title", "Read full article")),
            "source_name": str(article.get("source", "")),
            "url": safe_source_url(article.get("link")),
            "source_type": article.get("source_type", "trade_media"),
            "official": bool(article.get("official", False)),
            "airline": str(article.get("airline", "")),
            "topics": article.get("topics", []),
            "license_required": bool(article.get("license_required", False)),
            "license_status": str(article.get("license_status", "public")),
            "region": str(article.get("region", "Global")),
            "tier": article.get("tier"),
            "reliability_weight": article.get("reliability_weight"),
        },
        "related_news": [],
        "narrative_status": "pending",
        **({"basis": article["basis"]} if article.get("basis") else {}),
        **({"context_demoted_from": article["context_demoted_from"]} if article.get("context_demoted_from") else {}),
    }


def fallback_briefing(articles, mode="daily", warning="AI analysis is unavailable."):
    """Return only real source material when AI analysis cannot be produced."""
    mode = validate_mode(mode)
    stories = []
    for index, article in enumerate(articles[:10], start=1):
        if not isinstance(article, dict):
            continue
        story = build_candidate_story(article, index)
        for key in ("source_description", "narrative_status"):
            story.pop(key, None)
        story["lead"] = str(article.get("description", ""))
        stories.append(story)
    status = "degraded" if stories else "unavailable"
    return build_briefing_payload(mode, stories, status=status, warning=warning)


def collect_run(market_database=None, recovered=None, deep_scan=None):
    """One collection pass shared by every mode: sources, market panel, entities, scores, selection.

    Raises only when data collection itself failed. No LLM is involved; the LLM step comes later and
    may fail without affecting anything returned here.
    """
    is_deep = story_lifecycle.is_morning_deep_window(utc_now()) if deep_scan is None else bool(deep_scan)
    local_market_database = market_data.database_path(market_database)
    # The CSV files in config/ are the source of truth; SQLite is rebuilt from them on every run.
    source_registry.sync_sources_from_csv()
    entity_index = entities.EntityIndex.from_csv()
    entities.sync_entities(local_market_database)
    # Commentary on market events stays template-based: it keeps the run's LLM budget for story narratives.
    market_panel = market_data.refresh_market_data(local_market_database, eia_api_key=_env_value("EIA_API_KEY"), gemini_api_key="", fred_api_key=_env_value("FRED_API_KEY"))
    source_report = {}
    articles = fetch_rss_items(max_hours=48, report=source_report, recovered=recovered)
    if not articles:
        raise RuntimeError("No articles could be collected from any source")
    market_data.record_article_events(local_market_database, articles)
    entities.annotate_articles(articles, entity_index)
    safety_context.enforce(articles)

    candidates = [build_candidate_story(article, index) for index, article in enumerate(story_lifecycle.cluster_representatives(articles), start=1)]
    story_lifecycle.enrich_stories(candidates, articles)
    relevance_config = story_lifecycle.load_relevance_config()
    selection_cfg = dict(relevance_config["selection"])
    if is_deep:
        selection_cfg["max_per_run"] = max(22, int(selection_cfg.get("max_per_run", 18)))
    selected = story_lifecycle.select_stories(candidates, selection_cfg, relevance_config.get("commentary"))
    source_registry.record_source_statistics(articles, {"stories": selected})
    print(f"{len(articles)} articles, {len(candidates)} candidate stories, {len(selected)} above the score threshold (deep_scan={is_deep})")
    return {
        "stories": selected,
        "market": market_panel,
        "articles": len(articles),
        "candidates": len(candidates),
        "source_report": source_report,
        "morning_deep_scan": is_deep,
    }


def _write_local_briefing_cache(briefing, mode):
    cache_path = CACHE_FILE_HOURLY if mode == "hourly" else CACHE_FILE_DAILY
    try:
        with open(cache_path, "w", encoding="utf-8") as cache_file:
            json.dump(briefing, cache_file, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"Önbellek yazma hatası: {exc}")


def run_pipeline(mode="daily", market_database=None):
    """Run collection and analysis only in the scheduled worker or local maintenance flow."""
    mode = validate_mode(mode)
    print(f"Havacılık haberleri toplanıyor (Mod: {mode})...")
    local_market_database = market_data.database_path(market_database)
    # The CSV files in config/ are the source of truth; SQLite is rebuilt from them on every run.
    source_registry.sync_sources_from_csv()
    entity_index = entities.EntityIndex.from_csv()
    entities.sync_entities(local_market_database)
    market_panel = market_data.refresh_market_data(
        local_market_database,
        eia_api_key=_env_value("EIA_API_KEY"),
        fred_api_key=_env_value("FRED_API_KEY"),
        gemini_api_key=GEMINI_API_KEY,
    )
    articles = fetch_rss_items(max_hours=48 if mode == "daily" else 2)
    market_data.record_article_events(local_market_database, articles)
    entities.annotate_articles(articles, entity_index)
    safety_context.enforce(articles)
    print(f"{len(articles)} haber maddesi toplandı. Analiz ediliyor...")
    briefing = generate_briefing_with_gemini(articles, mode=mode)
    story_lifecycle.enrich_stories(briefing["stories"], articles)
    if mode == "daily":
        source_registry.record_source_statistics(articles, briefing)
    briefing["market"] = market_panel
    briefing["last_pipeline_run_at"] = utc_now().isoformat()
    _write_local_briefing_cache(briefing, mode)
    return briefing


def _read_local_briefing_cache(mode):
    cache_path = CACHE_FILE_HOURLY if mode == "hourly" else CACHE_FILE_DAILY
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if data.get("mode") == mode else None


class BriefingNotFound(LookupError):
    """No archive file exists for the requested day."""


def get_ready_briefing(mode="daily", date=None, include_low=False):
    """Read a completed briefing; this function never collects feeds or calls an LLM.

    date=None serves today's archive (latest.json); date="YYYY-MM-DD" serves that day and raises
    LookupError when no archive exists for it. Badges, score bands and ordering are recomputed on every
    read; the archive-only low band is returned only with include_low. The default daily view contains only stories
    published in Istanbul's current calendar day. Historical archive files themselves are never pruned.
    """
    mode = validate_mode(mode)
    if date is not None:
        story_lifecycle.validate_date(date)
    now = story_lifecycle.utc_now()
    config = story_lifecycle.load_badges_config()
    today = story_lifecycle.day_key(now, config)
    snapshot_path = briefing_store.latest_path() if date is None else briefing_store.day_path(date)
    snapshot = briefing_store.read_json(snapshot_path)
    pipeline_status = briefing_store.read_json(briefing_store.status_path()) or {}
    store_unreadable = not isinstance(snapshot, dict)
    if store_unreadable and date is not None:
        raise BriefingNotFound(f"no briefing archive for {date}")
    if store_unreadable:
        snapshot = _read_local_briefing_cache(mode)
    if not isinstance(snapshot, dict):
        return build_briefing_payload(mode, [], status="unavailable", warning="No completed pipeline snapshot is available yet.")

    snapshot["last_pipeline_run_at"] = snapshot.get("last_pipeline_run_at") or snapshot.get("generated_at", "")
    is_archive = bool(snapshot.get("date"))
    if is_archive:
        # Current exclusion lists apply at read time; nothing is removed from the archive file itself.
        snapshot["excluded_count"] = story_lifecycle.drop_excluded(snapshot)
        snapshot = story_lifecycle.present_stories(snapshot, now, config)
        snapshot["older_archive_count"] = 0
        if mode == "daily" and date is None and snapshot["date"] == today:
            snapshot["older_archive_count"] = story_lifecycle.drop_not_published_on_day(snapshot, today, config)
        for story in snapshot["stories"]:
            if story.get("basis") == feed_sources.BASIS_HEADLINE_ONLY:
                story["source_description"] = ""
        everything = snapshot["stories"]
        if not include_low:
            snapshot["stories"] = [story for story in everything if story_lifecycle.is_listed(story)]
        snapshot["hidden_low_count"] = len(everything) - len(snapshot["stories"])
        snapshot["yesterday_count"] = 0
        if mode == "hourly" and snapshot["date"] == today:
            snapshot = story_lifecycle.hourly_view(snapshot, now, config)
        snapshot["mode"] = mode
    snapshot["market"] = market_data.apply_display_settings(snapshot.get("market"))
    if store_unreadable:
        snapshot["status"] = "stale"
        snapshot["warning"] = "The live briefing data could not be read; the last committed snapshot is shown."
    elif date is None and is_archive and snapshot["date"] != today:
        snapshot["status"] = "stale"
        snapshot["warning"] = "No briefing has been published for today yet; the latest archived day is shown."
    elif date is None and pipeline_status.get("status") == "stale":
        snapshot["status"] = "stale"
        snapshot["warning"] = "The latest pipeline attempt failed; the last successful briefing is shown."
        snapshot["last_pipeline_attempt_at"] = pipeline_status.get("last_attempt_at", "")
    return snapshot


def get_briefing(mode="daily", force_refresh=False, date=None, include_low=False):
    """Compatibility wrapper: only an explicit local maintenance call may generate data."""
    if force_refresh:
        return run_pipeline(mode)
    return get_ready_briefing(mode, date=date, include_low=include_low)


def wants_low(query):
    """?include_low=1 (or true) asks for the archive-only low band as well."""
    return str((query.get("include_low") or [""])[0]).lower() in {"1", "true", "yes"}

if __name__ == "__main__":
    print("Aviation Briefing Engine test ediliyor...")
    res = run_pipeline(mode="daily")
    print(f"Başarılı! {len(res['stories'])} haber oluşturuldu.")
    print("Başlık:", res["heading"])
    for s in res["stories"]:
        print(f" - [{s['section']}] {s['headline']}")
